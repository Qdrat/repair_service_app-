from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Настройки базы данных
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:310807@localhost:5432/repair_service"
)
# DATABASE_URL = "postgresql://postgres:310807@localhost:5432/dbname"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Создает все таблицы в базе данных"""
    Base.metadata.create_all(bind=engine)