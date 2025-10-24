from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional

from database import get_db
from models import Service, ServiceOffering, ServiceArea, User, VerificationStatus
from schemas import ServiceCreate, ServiceResponse, ServiceOfferingCreate, ServiceOfferingResponse
from auth import get_current_active_user

router = APIRouter()


@router.post("/", response_model=ServiceResponse)
async def create_service(
        service_data: ServiceCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Создание нового сервиса"""
    try:
        # Проверяем, что пользователь может создавать сервисы
        if current_user.role not in ["service", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только сервисы и администраторы могут создавать сервисы"
            )

        # Проверяем, что у пользователя еще нет сервиса
        existing_service = db.query(Service).filter(Service.user_id == current_user.id).first()
        if existing_service and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У пользователя уже есть сервис"
            )

        # Создаем сервис
        service = Service(
            user_id=current_user.id,
            company_name=service_data.company_name,
            inn=service_data.inn,
            activity_type=service_data.activity_type,
            description=service_data.description,
            phone=service_data.phone,
            email=service_data.email,
            bank_account=service_data.bank_account,
            bank_bik=service_data.bank_bik,
            verification_status=VerificationStatus.PENDING
        )

        db.add(service)
        db.commit()
        db.refresh(service)

        return service

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании сервиса: {str(e)}"
        )


@router.get("/", response_model=List[ServiceResponse])
async def get_services(
        activity_type: Optional[str] = None,
        verification_status: Optional[VerificationStatus] = None,
        min_rating: Optional[float] = None,
        db: Session = Depends(get_db)
):
    """Получение списка сервисов с фильтрацией"""
    query = db.query(Service)

    # Фильтрация по типу деятельности
    if activity_type:
        query = query.filter(Service.activity_type == activity_type)

    # Фильтрация по статусу верификации
    if verification_status:
        query = query.filter(Service.verification_status == verification_status)

    # Фильтрация по минимальному рейтингу
    if min_rating is not None:
        query = query.filter(Service.average_rating >= min_rating)

    services = query.order_by(Service.average_rating.desc()).all()
    return services


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(service_id: int, db: Session = Depends(get_db)):
    """Получение сервиса по ID"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сервис не найден"
        )

    return service


@router.put("/{service_id}", response_model=ServiceResponse)
async def update_service(
        service_id: int,
        service_update: ServiceCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Обновление сервиса"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сервис не найден"
        )

    # Проверяем права на обновление
    if current_user.role != "admin" and service.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на обновление этого сервиса"
        )

    # Обновляем поля
    update_data = service_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)

    return service


@router.put("/{service_id}/verification")
async def update_service_verification(
        service_id: int,
        verification_status: VerificationStatus,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Изменение статуса верификации сервиса (только для админов)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только администраторы могут изменять статус верификации"
        )

    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сервис не найден"
        )

    service.verification_status = verification_status
    db.commit()

    return {"message": f"Статус верификации изменен на {verification_status}"}


# Управление услугами сервиса
@router.post("/{service_id}/offerings", response_model=ServiceOfferingResponse)
async def create_service_offering(
        service_id: int,
        offering_data: ServiceOfferingCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Создание новой услуги для сервиса"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сервис не найден"
        )

    # Проверяем права на создание услуги
    if current_user.role != "admin" and service.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на создание услуг для этого сервиса"
        )

    offering = ServiceOffering(
        service_id=service_id,
        name=offering_data.name,
        price=offering_data.price,
        duration_days=offering_data.duration_days,
        description=offering_data.description
    )

    db.add(offering)
    db.commit()
    db.refresh(offering)

    return offering


@router.get("/{service_id}/offerings", response_model=List[ServiceOfferingResponse])
async def get_service_offerings(service_id: int, db: Session = Depends(get_db)):
    """Получение списка услуг сервиса"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сервис не найден"
        )

    offerings = db.query(ServiceOffering).filter(
        ServiceOffering.service_id == service_id,
        ServiceOffering.is_active == True
    ).all()

    return offerings


@router.put("/{service_id}/offerings/{offering_id}", response_model=ServiceOfferingResponse)
async def update_service_offering(
        service_id: int,
        offering_id: int,
        offering_update: ServiceOfferingCreate,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Обновление услуги сервиса"""
    offering = db.query(ServiceOffering).filter(
        ServiceOffering.id == offering_id,
        ServiceOffering.service_id == service_id
    ).first()

    if not offering:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Услуга не найдена"
        )

    # Проверяем права на обновление
    service = db.query(Service).filter(Service.id == service_id).first()
    if current_user.role != "admin" and service.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на обновление этой услуги"
        )

    # Обновляем поля
    update_data = offering_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(offering, field, value)

    db.commit()
    db.refresh(offering)

    return offering


@router.delete("/{service_id}/offerings/{offering_id}")
async def delete_service_offering(
        service_id: int,
        offering_id: int,
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
):
    """Удаление услуги сервиса (деактивация)"""
    offering = db.query(ServiceOffering).filter(
        ServiceOffering.id == offering_id,
        ServiceOffering.service_id == service_id
    ).first()

    if not offering:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Услуга не найдена"
        )

    # Проверяем права на удаление
    service = db.query(Service).filter(Service.id == service_id).first()
    if current_user.role != "admin" and service.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на удаление этой услуги"
        )

    offering.is_active = False
    db.commit()

    return {"message": "Услуга деактивирована"}