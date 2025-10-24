from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class UserRole(str, enum.Enum):
    CLIENT = "client"
    SERVICE = "service"
    PVZ = "pvz"
    ADMIN = "admin"


class OrderStatus(str, enum.Enum):
    CREATED = "created"
    RECEIVED = "received"
    SENT_TO_SERVICE = "sent_to_service"
    DIAGNOSING = "diagnosing"
    PRICE_PROPOSED = "price_proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    IN_WORK = "in_work"
    READY = "ready"
    READY_FOR_PICKUP = "ready_for_pickup"
    DELIVERED = "delivered"


class OrderCategory(str, enum.Enum):
    TECH = "tech"
    CLOTHES = "clothes"
    SHOES = "shoes"


class PaymentMethod(str, enum.Enum):
    ONLINE = "online"
    CASH = "cash"


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, unique=True, index=True)
    role = Column(String, nullable=False, default="CLIENT")  # Обновите значение по умолчанию
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True)

    # Связи
    orders = relationship("Order", back_populates="user", foreign_keys="Order.user_id")
    service_orders = relationship("Order", back_populates="service", foreign_keys="Order.service_id")
    reviews = relationship("Review", back_populates="client")
    received_reviews = relationship("Review", back_populates="service")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_name = Column(String, nullable=False)
    inn = Column(String, nullable=True)
    activity_type = Column(String, nullable=False)  # ремонт, химчистка, ателье, обувь
    description = Column(Text, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    verification_status = Column(SQLEnum(VerificationStatus), default=VerificationStatus.PENDING)
    bank_account = Column(String, nullable=True)
    bank_bik = Column(String, nullable=True)
    average_rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("User")
    services_offered = relationship("ServiceOffering", back_populates="service")
    service_areas = relationship("ServiceArea", back_populates="service")


class PVZ(Base):
    __tablename__ = "pvz"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    working_hours = Column(String, nullable=False)
    operator_name = Column(String, nullable=True)
    operator_phone = Column(String, nullable=True)
    accepts_tech = Column(Boolean, default=True)
    accepts_clothes = Column(Boolean, default=True)
    accepts_shoes = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("User")
    orders_received = relationship("Order", back_populates="receive_pvz", foreign_keys="Order.receive_pvz_id")
    orders_delivered = relationship("Order", back_populates="delivery_pvz", foreign_keys="Order.delivery_pvz_id")


class ServiceOffering(Base):
    __tablename__ = "service_offerings"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=True)  # None если "цена уточняется"
    duration_days = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    service = relationship("Service", back_populates="services_offered")


class ServiceArea(Base):
    __tablename__ = "service_areas"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    area_name = Column(String, nullable=False)
    radius_km = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    service = relationship("Service", back_populates="service_areas")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    order_number = Column(String, unique=True, index=True, nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    receive_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    delivery_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)

    category = Column(SQLEnum(OrderCategory), nullable=False)
    subcategory = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    photos = Column(Text, nullable=True)  # JSON список URL фото
    price_limit = Column(Float, nullable=True)
    proposed_price = Column(Float, nullable=True)
    final_price = Column(Float, nullable=True)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)

    status = Column(SQLEnum(OrderStatus), default=OrderStatus.CREATED)
    price_justification = Column(Text, nullable=True)
    qr_code = Column(String, nullable=True)
    short_id = Column(String, nullable=True)  # Для маркировки (например, "7X9")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    received_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Связи
    user = relationship("User", back_populates="orders", foreign_keys=[user_id])
    client = relationship("User", back_populates="orders", foreign_keys=[client_id])
    service = relationship("User", back_populates="service_orders", foreign_keys=[service_id])
    receive_pvz = relationship("PVZ", back_populates="orders_received", foreign_keys=[receive_pvz_id])
    delivery_pvz = relationship("PVZ", back_populates="orders_delivered", foreign_keys=[delivery_pvz_id])
    reviews = relationship("Review", back_populates="order")
    order_photos = relationship("OrderPhoto", back_populates="order")


class OrderPhoto(Base):
    __tablename__ = "order_photos"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    photo_type = Column(String, nullable=False)  # "initial", "received", "delivered"
    photo_url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    order = relationship("Order", back_populates="order_photos")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5
    text = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    order = relationship("Order", back_populates="reviews")
    client = relationship("User", back_populates="reviews", foreign_keys=[client_id])
    service = relationship("User", back_populates="received_reviews", foreign_keys=[service_id])


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    order = relationship("Order")
    sender = relationship("User")