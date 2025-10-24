from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
import os
from datetime import datetime

from database import get_db
from models import Order, User, PVZ, OrderPhoto, OrderStatus
from schemas import OrderCreate, OrderUpdate, OrderResponse, OrderWithPhotos
from auth import get_current_active_user
from config import settings

router = APIRouter()


@router.post("/", response_model=OrderResponse)
async def create_order(
        order_data: OrderCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Создание нового заказа"""
    try:
        # Проверяем, что пользователь - клиент
        if current_user.role != "client":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только клиенты могут создавать заказы"
            )

        # Проверяем существование ПВЗ
        receive_pvz = db.query(PVZ).filter(PVZ.id == order_data.receive_pvz_id).first()
        delivery_pvz = db.query(PVZ).filter(PVZ.id == order_data.delivery_pvz_id).first()

        if not receive_pvz or not delivery_pvz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ПВЗ не найден"
            )

        # Генерируем номер заказа
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Создаем заказ
        order = Order(
            order_number=order_number,
            client_id=current_user.id,
            receive_pvz_id=order_data.receive_pvz_id,
            delivery_pvz_id=order_data.delivery_pvz_id,
            category=order_data.category,
            subcategory=order_data.subcategory,
            description=order_data.description,
            price_limit=order_data.price_limit,
            payment_method=order_data.payment_method,
            status=OrderStatus.CREATED
        )

        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании заказа: {str(e)}"
        )


@router.get("/", response_model=List[OrderResponse])
async def get_orders(
        status_filter: Optional[OrderStatus] = None,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Получение списка заказов"""
    query = db.query(Order)

    # Фильтрация по роли пользователя
    if current_user.role == "client":
        query = query.filter(Order.client_id == current_user.id)
    elif current_user.role == "service":
        query = query.filter(Order.service_id == current_user.id)
    elif current_user.role == "pvz":
        # ПВЗ видит заказы, которые они принимают или доставляют
        query = query.filter(
            (Order.receive_pvz_id.in_(
                db.query(PVZ.id).filter(PVZ.user_id == current_user.id)
            )) |
            (Order.delivery_pvz_id.in_(
                db.query(PVZ.id).filter(PVZ.user_id == current_user.id)
            ))
        )

    # Фильтрация по статусу
    if status_filter:
        query = query.filter(Order.status == status_filter)

    orders = query.order_by(Order.created_at.desc()).all()
    return orders


@router.get("/{order_id}", response_model=OrderWithPhotos)
async def get_order(
        order_id: int,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Получение заказа по ID"""
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заказ не найден"
        )

    # Проверяем права доступа
    has_access = False
    if current_user.role == "client" and order.client_id == current_user.id:
        has_access = True
    elif current_user.role == "service" and order.service_id == current_user.id:
        has_access = True
    elif current_user.role == "pvz":
        pvz_ids = db.query(PVZ.id).filter(PVZ.user_id == current_user.id).all()
        if order.receive_pvz_id in [p[0] for p in pvz_ids] or order.delivery_pvz_id in [p[0] for p in pvz_ids]:
            has_access = True

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому заказу"
        )

    # Получаем фото заказа
    photos = db.query(OrderPhoto).filter(OrderPhoto.order_id == order_id).all()
    photo_urls = [photo.photo_url for photo in photos]

    order_dict = order.__dict__.copy()
    order_dict['photos'] = photo_urls

    return order_dict


@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
        order_id: int,
        order_update: OrderUpdate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Обновление заказа"""
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заказ не найден"
        )

    # Проверяем права на обновление
    can_update = False
    if current_user.role == "client" and order.client_id == current_user.id:
        # Клиент может обновлять только определенные поля
        can_update = True
    elif current_user.role == "service" and order.service_id == current_user.id:
        can_update = True
    elif current_user.role == "admin":
        can_update = True

    if not can_update:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на обновление заказа"
        )

    # Обновляем поля
    update_data = order_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)

    return order


@router.post("/{order_id}/photos")
async def upload_order_photos(
        order_id: int,
        files: List[UploadFile] = File(...),
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Загрузка фотографий для заказа"""
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Заказ не найден"
        )

    # Проверяем права доступа
    if current_user.role == "client" and order.client_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к этому заказу"
        )

    # Создаем директорию для загрузок
    upload_dir = os.path.join(settings.UPLOAD_DIR, f"order_{order_id}")
    os.makedirs(upload_dir, exist_ok=True)

    uploaded_files = []

    for file in files:
        # Проверяем размер файла
        if file.size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Файл {file.filename} слишком большой"
            )

        # Генерируем уникальное имя файла
        file_extension = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_dir, filename)

        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Сохраняем информацию о файле в базе
        photo_url = f"/uploads/order_{order_id}/{filename}"
        order_photo = OrderPhoto(
            order_id=order_id,
            photo_type="initial",
            photo_url=photo_url
        )
        db.add(order_photo)
        uploaded_files.append(photo_url)

    db.commit()

    return {"message": "Фотографии загружены", "files": uploaded_files}