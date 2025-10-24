from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import User, UserRole
from schemas import UserUpdate, UserResponse
from auth import get_current_active_user

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: User = Depends(get_current_active_user)):
    """Получение информации о текущем пользователе"""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
        user_update: UserUpdate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Обновление информации о текущем пользователе"""
    try:
        # Обновляем только разрешенные поля
        update_data = user_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(current_user, field, value)

        db.commit()
        db.refresh(current_user)

        return current_user

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении профиля: {str(e)}"
        )


@router.get("/", response_model=List[UserResponse])
async def get_users(
        role: Optional[UserRole] = None,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Получение списка пользователей (только для админов)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы могут просматривать список пользователей"
        )

    query = db.query(User)
    if role:
        query = query.filter(User.role == role)

    users = query.filter(User.is_active == True).all()
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
        user_id: int,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Получение пользователя по ID"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Проверяем права доступа
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к информации о пользователе"
        )

    return user


@router.put("/{user_id}/status")
async def update_user_status(
        user_id: int,
        is_active: bool,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Изменение статуса пользователя (только для админов)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы могут изменять статус пользователей"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    user.is_active = is_active
    db.commit()

    return {"message": f"Статус пользователя изменен на {'активный' if is_active else 'неактивный'}"}