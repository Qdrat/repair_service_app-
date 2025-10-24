from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from models import User
import secrets

# Настройки JWT
SECRET_KEY = "your-secret-key-change-in-production"  # Замените в продакшене!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    Проверяет JWT токен и возвращает phone_number если токен валиден
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone_number: str = payload.get("sub")
        if phone_number is None:
            return None
        return phone_number
    except JWTError:
        return None


async def get_current_active_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    from sqlalchemy import text

    token = credentials.credentials
    phone_number = verify_token(token)
    if phone_number is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Сначала попробуем получить только базовые поля
    stmt = text("""
        SELECT id, phone_number, role, is_active, created_at
        FROM users 
        WHERE phone_number = :phone
    """)
    result = db.execute(stmt, {"phone": phone_number})
    user_data = result.fetchone()

    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    # Создаем словарь с данными пользователя
    user_dict = {
        "id": user_data[0],
        "phone_number": user_data[1],
        "role": user_data[2],
        "is_active": user_data[3],
        "created_at": user_data[4],
        # Добавляем поля по умолчанию для отсутствующих столбцов
        "first_name": None,
        "last_name": None,
        "email": None
    }

    if not user_dict["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неактивный пользователь",
        )

    return user_dict

def generate_sms_code(length: int = 4) -> str:
    """Генерирует случайный SMS код"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(length)])


def send_sms(phone_number: str, code: str) -> bool:
    """Функция отправки SMS (заглушка для разработки)"""
    try:
        # В реальном приложении здесь будет интеграция с SMS-сервисом
        print(f"SMS sent to {phone_number}: Your code is {code}")
        return True
    except Exception as e:
        print(f"SMS sending failed: {e}")
        return False