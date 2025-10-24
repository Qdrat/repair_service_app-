from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional
from geopy.distance import geodesic

from database import get_db
from models import PVZ, User
from schemas import PVZCreate, PVZResponse
from auth import get_current_active_user

router = APIRouter()


@router.post("/", response_model=PVZResponse)
async def create_pvz(
        pvz_data: PVZCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Создание нового ПВЗ"""
    try:
        # Проверяем, что пользователь может создавать ПВЗ
        if current_user.role not in ["pvz", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только ПВЗ и администраторы могут создавать пункты выдачи"
            )

        # Проверяем, что у пользователя еще нет ПВЗ
        existing_pvz = db.query(PVZ).filter(PVZ.user_id == current_user.id).first()
        if existing_pvz and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У пользователя уже есть ПВЗ"
            )

        # Создаем ПВЗ
        pvz = PVZ(
            user_id=current_user.id,
            name=pvz_data.name,
            address=pvz_data.address,
            latitude=pvz_data.latitude,
            longitude=pvz_data.longitude,
            working_hours=pvz_data.working_hours,
            operator_name=pvz_data.operator_name,
            operator_phone=pvz_data.operator_phone,
            accepts_tech=pvz_data.accepts_tech,
            accepts_clothes=pvz_data.accepts_clothes,
            accepts_shoes=pvz_data.accepts_shoes,
            is_active=True
        )

        db.add(pvz)
        db.commit()
        db.refresh(pvz)

        return pvz

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании ПВЗ: {str(e)}"
        )


@router.get("/", response_model=List[PVZResponse])
async def get_pvz_list(
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = 10,
        accepts_tech: Optional[bool] = None,
        accepts_clothes: Optional[bool] = None,
        accepts_shoes: Optional[bool] = None,
        db: Session = Depends(get_db)
):
    """Получение списка ПВЗ с возможностью фильтрации по местоположению"""
    query = db.query(PVZ).filter(PVZ.is_active == True)

    # Фильтрация по типу принимаемых товаров
    if accepts_tech is not None:
        query = query.filter(PVZ.accepts_tech == accepts_tech)
    if accepts_clothes is not None:
        query = query.filter(PVZ.accepts_clothes == accepts_clothes)
    if accepts_shoes is not None:
        query = query.filter(PVZ.accepts_shoes == accepts_shoes)

    pvz_list = query.all()

    # Фильтрация по расстоянию, если указаны координаты
    if latitude is not None and longitude is not None:
        user_location = (latitude, longitude)
        filtered_pvz = []

        for pvz in pvz_list:
            pvz_location = (pvz.latitude, pvz.longitude)
            distance = geodesic(user_location, pvz_location).kilometers

            if distance <= radius_km:
                # Добавляем расстояние к объекту ПВЗ
                pvz_dict = pvz.__dict__.copy()
                pvz_dict['distance_km'] = round(distance, 2)
                filtered_pvz.append(pvz_dict)

        # Сортируем по расстоянию
        filtered_pvz.sort(key=lambda x: x['distance_km'])
        return filtered_pvz

    return pvz_list


@router.get("/{pvz_id}", response_model=PVZResponse)
async def get_pvz(pvz_id: int, db: Session = Depends(get_db)):
    """Получение ПВЗ по ID"""
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()

    if not pvz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ПВЗ не найден"
        )

    return pvz


@router.put("/{pvz_id}", response_model=PVZResponse)
async def update_pvz(
        pvz_id: int,
        pvz_update: PVZCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Обновление ПВЗ"""
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()

    if not pvz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ПВЗ не найден"
        )

    # Проверяем права на обновление
    if current_user.role != "admin" and pvz.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на обновление этого ПВЗ"
        )

    # Обновляем поля
    update_data = pvz_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pvz, field, value)

    db.commit()
    db.refresh(pvz)

    return pvz


@router.put("/{pvz_id}/status")
async def update_pvz_status(
        pvz_id: int,
        is_active: bool,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Изменение статуса ПВЗ"""
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()

    if not pvz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ПВЗ не найден"
        )

    # Проверяем права на изменение статуса
    if current_user.role != "admin" and pvz.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на изменение статуса этого ПВЗ"
        )

    pvz.is_active = is_active
    db.commit()

    return {"message": f"Статус ПВЗ изменен на {'активный' if is_active else 'неактивный'}"}


@router.get("/nearby/")
async def get_nearby_pvz(
        latitude: float,
        longitude: float,
        radius_km: float = 5,
        category: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """Получение ближайших ПВЗ с поддержкой категорий"""
    user_location = (latitude, longitude)

    query = db.query(PVZ).filter(PVZ.is_active == True)

    # Фильтрация по категории
    if category:
        if category == "tech":
            query = query.filter(PVZ.accepts_tech == True)
        elif category == "clothes":
            query = query.filter(PVZ.accepts_clothes == True)
        elif category == "shoes":
            query = query.filter(PVZ.accepts_shoes == True)

    pvz_list = query.all()
    nearby_pvz = []

    for pvz in pvz_list:
        pvz_location = (pvz.latitude, pvz.longitude)
        distance = geodesic(user_location, pvz_location).kilometers

        if distance <= radius_km:
            pvz_dict = pvz.__dict__.copy()
            pvz_dict['distance_km'] = round(distance, 2)
            nearby_pvz.append(pvz_dict)

    # Сортируем по расстоянию
    nearby_pvz.sort(key=lambda x: x['distance_km'])

    return {
        "user_location": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "pvz_count": len(nearby_pvz),
        "pvz_list": nearby_pvz
    }