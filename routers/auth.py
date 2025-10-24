from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import redis
import json
from typing import Optional
import logging
import time

from database import get_db
from models import User
from schemas import PhoneAuth, SMSCode, Token, UserResponse
from auth import (
    create_access_token,
    verify_token,
    get_current_active_user,
    generate_sms_code,
    send_sms,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from config import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# In-memory хранилище для разработки (если Redis недоступен)
dev_sms_storage = {}
dev_storage_cleanup_time = time.time()


class SMSStorage:
    def __init__(self):
        self.redis_client = None
        self._init_redis()

    def _init_redis(self):
        """Инициализация подключения к Redis"""
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=getattr(settings, 'REDIS_PASSWORD', None),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self.redis_client.ping()
            logger.info("Redis подключен успешно")
        except Exception as e:
            logger.warning(f"Redis не доступен: {e}. Используется in-memory хранилище")
            self.redis_client = None

    def set_sms_code(self, phone_number: str, code: str, ttl: int = 300):
        """Сохраняет SMS код"""
        if self.redis_client:
            try:
                self.redis_client.setex(f"sms_code:{phone_number}", ttl, code)
                return True
            except Exception as e:
                logger.error(f"Ошибка сохранения в Redis: {e}")
                self.redis_client = None
                return self._set_sms_code_fallback(phone_number, code, ttl)
        else:
            return self._set_sms_code_fallback(phone_number, code, ttl)

    def _set_sms_code_fallback(self, phone_number: str, code: str, ttl: int):
        """Fallback сохранения в памяти"""
        try:
            dev_sms_storage[phone_number] = {
                'code': code,
                'expires': time.time() + ttl
            }
            logger.info(f"Код сохранен в памяти для {phone_number}")
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения в памяти: {e}")
            return False

    def get_sms_code(self, phone_number: str) -> Optional[str]:
        """Получает SMS код"""
        if self.redis_client:
            try:
                return self.redis_client.get(f"sms_code:{phone_number}")
            except Exception as e:
                logger.error(f"Ошибка чтения из Redis: {e}")
                self.redis_client = None
                return self._get_sms_code_fallback(phone_number)
        else:
            return self._get_sms_code_fallback(phone_number)

    def _get_sms_code_fallback(self, phone_number: str) -> Optional[str]:
        """Fallback чтения из памяти"""
        try:
            global dev_storage_cleanup_time

            # Очистка устаревших кодов каждые 5 минут
            if time.time() - dev_storage_cleanup_time > 300:
                self._cleanup_expired_codes()
                dev_storage_cleanup_time = time.time()

            data = dev_sms_storage.get(phone_number)
            if data and time.time() < data['expires']:
                return data['code']
            elif phone_number in dev_sms_storage:
                del dev_sms_storage[phone_number]
            return None
        except Exception as e:
            logger.error(f"Ошибка чтения из памяти: {e}")
            return None

    def delete_sms_code(self, phone_number: str):
        """Удаляет SMS код"""
        if self.redis_client:
            try:
                self.redis_client.delete(f"sms_code:{phone_number}")
            except Exception as e:
                logger.error(f"Ошибка удаления из Redis: {e}")
                self.redis_client = None
                self._delete_sms_code_fallback(phone_number)
        else:
            self._delete_sms_code_fallback(phone_number)

    def _delete_sms_code_fallback(self, phone_number: str):
        """Fallback удаления из памяти"""
        try:
            if phone_number in dev_sms_storage:
                del dev_sms_storage[phone_number]
        except Exception as e:
            logger.error(f"Ошибка удаления из памяти: {e}")

    def _cleanup_expired_codes(self):
        """Очистка устаревших кодов"""
        try:
            current_time = time.time()
            expired_phones = [
                phone for phone, data in dev_sms_storage.items()
                if current_time >= data['expires']
            ]
            for phone in expired_phones:
                del dev_sms_storage[phone]
            if expired_phones:
                logger.info(f"Очищено {len(expired_phones)} устаревших кодов")
        except Exception as e:
            logger.error(f"Ошибка очистки кодов: {e}")


# Инициализация хранилища
sms_storage = SMSStorage()


@router.post("/send-sms", response_model=dict)
async def send_sms_code(phone_auth: PhoneAuth, db: Session = Depends(get_db)):
    """Отправка SMS кода для аутентификации"""
    try:
        logger.info(f"Получен запрос на отправку SMS для: {phone_auth.phone_number}")

        # Генерируем код
        code = generate_sms_code()
        logger.info(f"Сгенерирован код: {code} для номера: {phone_auth.phone_number}")

        # Сохраняем код
        if not sms_storage.set_sms_code(phone_auth.phone_number, code):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка сохранения кода"
            )

        # Отправляем SMS
        logger.info(f"Попытка отправки SMS на {phone_auth.phone_number}")
        try:
            sms_result = send_sms(phone_auth.phone_number, code)
        except Exception as e:
            logger.error(f"Исключение при отправке SMS: {e}")
            sms_result = False

        if sms_result:
            logger.info(f"SMS успешно отправлено на {phone_auth.phone_number}")
            return {
                "message": "SMS код отправлен",
                "phone_number": phone_auth.phone_number,
                "code": code  # Только для разработки!
            }
        else:
            logger.error(f"Ошибка отправки SMS на {phone_auth.phone_number}")
            # Удаляем код если SMS не отправлено
            sms_storage.delete_sms_code(phone_auth.phone_number)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка отправки SMS"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке SMS: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Внутренняя ошибка сервера"
        )


@router.post("/verify", response_model=Token)
async def verify_sms_code(sms_code: SMSCode, db: Session = Depends(get_db)):
    """Проверка SMS кода и выдача токена"""
    try:
        logger.info(f"Попытка верификации кода для: {sms_code.phone_number}")

        # Получаем код из хранилища
        stored_code = sms_storage.get_sms_code(sms_code.phone_number)
        logger.info(f"Получен код: {stored_code} для номера: {sms_code.phone_number}")

        if not stored_code:
            logger.warning(f"Код не найден для номера: {sms_code.phone_number}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Код не найден или истек. Запросите новый код."
            )

        # Удаляем код перед проверкой
        sms_storage.delete_sms_code(sms_code.phone_number)

        if stored_code != sms_code.code:
            logger.warning(
                f"Неверный код для {sms_code.phone_number}. Ожидался: {stored_code}, получен: {sms_code.code}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный код подтверждения"
            )

        logger.info(f"Код верный для {sms_code.phone_number}")

        # Полностью обходим ORM используя сырые SQL запросы
        from sqlalchemy import text

        # Проверяем существование пользователя
        check_stmt = text("SELECT id, is_active FROM users WHERE phone_number = :phone")
        result = db.execute(check_stmt, {"phone": sms_code.phone_number})
        user_data = result.fetchone()

        user_id = None

        if user_data:
            user_id = user_data[0]
            is_active = user_data[1]

            if not is_active:
                logger.warning(f"Попытка входа заблокированного пользователя: {sms_code.phone_number}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Аккаунт заблокирован"
                )
        else:
            # Создаем нового пользователя с ролью CLIENT
            logger.info(f"Создание нового пользователя: {sms_code.phone_number}")

            try:
                # Создаем пользователя с ролью CLIENT
                insert_stmt = text("""
                    INSERT INTO users (phone_number, role, is_active) 
                    VALUES (:phone, 'CLIENT', true)
                    RETURNING id
                """)
                result = db.execute(insert_stmt, {"phone": sms_code.phone_number})
                user_id = result.scalar()
                db.commit()
                logger.info(f"Создан пользователь с ID: {user_id} и ролью: CLIENT")

            except Exception as create_error:
                logger.error(f"Ошибка при создании пользователя: {create_error}")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Не удалось создать пользователя в базе данных"
                )

        # Создаем токен
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": sms_code.phone_number},
            expires_delta=access_token_expires
        )

        logger.info(f"Успешная аутентификация для: {sms_code.phone_number}")
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при верификации: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при проверке кода"
        )

@router.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    redis_status = "connected" if sms_storage.redis_client and sms_storage.redis_client.ping() else "disconnected"
    storage_type = "redis" if redis_status == "connected" else "memory"

    return {
        "status": "healthy",
        "redis": redis_status,
        "storage_type": storage_type,
        "timestamp": datetime.now().isoformat(),
        "active_codes_in_memory": len(dev_sms_storage) if storage_type == "memory" else 0
    }


# Остальные эндпоинты остаются без изменений
@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    """Получение информации о текущем пользователе"""
    return current_user


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """Выход из системы"""
    return {"message": "Успешный выход из системы"}


@router.get("/check-phone/{phone_number}")
async def check_phone_exists(phone_number: str, db: Session = Depends(get_db)):
    """Проверка существования номера телефона"""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    return {"exists": user is not None}


@router.get("/debug/allowed-roles")
async def get_allowed_roles(db: Session = Depends(get_db)):
    """Получить допустимые значения ролей из базы данных"""
    from sqlalchemy import text
    try:
        # Попробуем несколько способов получить значения ENUM
        queries = [
            "SELECT unnest(enum_range(NULL::userrole)) as role",
            "SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole')",
            "SELECT DISTINCT role FROM users WHERE role IS NOT NULL"
        ]

        results = {}
        for i, query in enumerate(queries):
            try:
                stmt = text(query)
                result = db.execute(stmt)
                roles = [row[0] for row in result.fetchall()]
                results[f"query_{i}"] = {
                    "query": query,
                    "roles": roles
                }
            except Exception as e:
                results[f"query_{i}"] = {
                    "query": query,
                    "error": str(e)
                }

        return results
    except Exception as e:
        return {"error": str(e)}

@router.get("/debug/existing-users")
async def get_existing_users(db: Session = Depends(get_db)):
    """Посмотреть существующих пользователей и их роли"""
    from sqlalchemy import text
    try:
        stmt = text("SELECT id, phone_number, role, is_active FROM users LIMIT 10")
        result = db.execute(stmt)
        users = []
        for row in result.fetchall():
            users.append({
                "id": row[0],
                "phone_number": row[1],
                "role": row[2],
                "is_active": row[3]
            })
        return {"users": users}
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/db-check")
async def debug_db_check(db: Session = Depends(get_db)):
    """Проверка подключения к базе данных и структуры таблиц"""
    from sqlalchemy import text
    try:
        # Проверяем подключение
        db.execute(text("SELECT 1"))

        # Проверяем существование таблицы users
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            )
        """))
        users_table_exists = result.scalar()

        # Проверяем существование типа userrole
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM pg_type WHERE typname = 'userrole'
            )
        """))
        userrole_type_exists = result.scalar()

        return {
            "database_connection": "ok",
            "users_table_exists": users_table_exists,
            "userrole_type_exists": userrole_type_exists
        }
    except Exception as e:
        return {"database_connection": "error", "error": str(e)}


@router.get("/debug/enum-values")
async def get_enum_values(db: Session = Depends(get_db)):
    """Получить точные значения ENUM типа userrole"""
    from sqlalchemy import text
    try:
        # Способ 1: через pg_enum (самый надежный)
        stmt1 = text("""
            SELECT enumlabel 
            FROM pg_enum 
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole')
            ORDER BY enumsortorder
        """)
        result1 = db.execute(stmt1)
        enum_values_1 = [row[0] for row in result1.fetchall()]

        # Способ 2: через enum_range
        stmt2 = text("SELECT unnest(enum_range(NULL::userrole))")
        result2 = db.execute(stmt2)
        enum_values_2 = [row[0] for row in result2.fetchall()]

        # Способ 3: посмотреть существующие роли в таблице users
        stmt3 = text("SELECT DISTINCT role FROM users WHERE role IS NOT NULL")
        result3 = db.execute(stmt3)
        existing_roles = [row[0] for row in result3.fetchall()]

        return {
            "from_pg_enum": enum_values_1,
            "from_enum_range": enum_values_2,
            "existing_roles_in_table": existing_roles
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/debug/table-structure")
async def get_table_structure(db: Session = Depends(get_db)):
    """Получить структуру таблицы users"""
    from sqlalchemy import text
    try:
        stmt = text("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            ORDER BY ordinal_position
        """)
        result = db.execute(stmt)
        columns = []
        for row in result.fetchall():
            columns.append({
                "column_name": row[0],
                "data_type": row[1],
                "is_nullable": row[2],
                "column_default": row[3]
            })
        return {"table_structure": columns}
    except Exception as e:
        return {"error": str(e)}