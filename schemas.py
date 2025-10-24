from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime
from models import UserRole, OrderStatus, OrderCategory, PaymentMethod, VerificationStatus


# Базовые схемы
class UserBase(BaseModel):
    phone_number: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: UserRole


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserResponse(BaseModel):
    id: int
    phone_number: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# Схемы для аутентификации
class PhoneAuth(BaseModel):
    phone_number: str

    @validator('phone_number')
    def validate_phone(cls, v):
        # Улучшенная валидация российского номера
        import re
        # Удаляем все символы кроме цифр
        cleaned = re.sub(r'\D', '', v)

        # Проверяем различные форматы российских номеров
        if len(cleaned) == 11 and cleaned.startswith('7'):
            return f"+7 {cleaned[1:4]} {cleaned[4:7]}-{cleaned[7:9]}-{cleaned[9:11]}"
        elif len(cleaned) == 10 and cleaned.startswith('9'):
            return f"+7 {cleaned[0:3]} {cleaned[3:6]}-{cleaned[6:8]}-{cleaned[8:10]}"
        else:
            raise ValueError('Неверный формат российского номера телефона')


class SMSCode(BaseModel):
    phone_number: str
    code: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    phone_number: Optional[str] = None


# Схемы для сервисов
class ServiceBase(BaseModel):
    company_name: str
    inn: Optional[str] = None
    activity_type: str
    description: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class ServiceCreate(ServiceBase):
    bank_account: Optional[str] = None
    bank_bik: Optional[str] = None


class ServiceResponse(ServiceBase):
    id: int
    user_id: int
    verification_status: VerificationStatus
    average_rating: float
    total_reviews: int
    created_at: datetime

    class Config:
        from_attributes = True


class ServiceOfferingBase(BaseModel):
    name: str
    price: Optional[float] = None
    duration_days: int
    description: Optional[str] = None


class ServiceOfferingCreate(ServiceOfferingBase):
    pass


class ServiceOfferingResponse(ServiceOfferingBase):
    id: int
    service_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Схемы для ПВЗ
class PVZBase(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    working_hours: str
    operator_name: Optional[str] = None
    operator_phone: Optional[str] = None
    accepts_tech: bool = True
    accepts_clothes: bool = True
    accepts_shoes: bool = True


class PVZCreate(PVZBase):
    pass


class PVZResponse(PVZBase):
    id: int
    user_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Схемы для заказов
class OrderBase(BaseModel):
    category: OrderCategory
    subcategory: str
    description: str
    price_limit: Optional[float] = None
    payment_method: PaymentMethod


class OrderCreate(OrderBase):
    receive_pvz_id: int
    delivery_pvz_id: int


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    proposed_price: Optional[float] = None
    final_price: Optional[float] = None
    price_justification: Optional[str] = None
    service_id: Optional[int] = None


class OrderResponse(OrderBase):
    id: int
    order_number: str
    client_id: int
    service_id: Optional[int]
    receive_pvz_id: int
    delivery_pvz_id: int
    status: OrderStatus
    proposed_price: Optional[float]
    final_price: Optional[float]
    price_justification: Optional[str]
    qr_code: Optional[str]
    short_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    received_at: Optional[datetime]
    delivered_at: Optional[datetime]

    # Связанные объекты
    client: UserResponse
    service: Optional[UserResponse]
    receive_pvz: PVZResponse
    delivery_pvz: PVZResponse

    class Config:
        from_attributes = True


class OrderWithPhotos(OrderResponse):
    photos: List[str] = []

    @validator('photos', pre=True)
    def parse_photos(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except:
                return []
        return v or []


# Схемы для отзывов
class ReviewBase(BaseModel):
    rating: int
    text: Optional[str] = None

    @validator('rating')
    def validate_rating(cls, v):
        if v < 1 or v > 5:
            raise ValueError('Rating must be between 1 and 5')
        return v


class ReviewCreate(ReviewBase):
    order_id: int


class ReviewUpdate(BaseModel):
    rating: Optional[int] = None
    text: Optional[str] = None


class ReviewResponse(ReviewBase):
    id: int
    order_id: int
    client_id: int
    service_id: int
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Схемы для чата
class ChatMessageBase(BaseModel):
    message: str


class ChatMessageCreate(ChatMessageBase):
    order_id: int


class ChatMessageResponse(ChatMessageBase):
    id: int
    order_id: int
    sender_id: int
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True