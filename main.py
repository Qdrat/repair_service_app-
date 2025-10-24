from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from sqlalchemy.orm import Session
import uvicorn
from typing import Optional
import os
from dotenv import load_dotenv

from database import get_db, engine
from models import Base
from routers import auth, orders, users, pvz, services
from schemas import TokenData
from auth import verify_token

load_dotenv()

# Создание таблиц
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="Repair Service API",
    description="API для сервиса ремонта и чистки",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Подключение роутеров
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(orders.router, prefix="/orders", tags=["orders"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(pvz.router, prefix="/pvz", tags=["pvz"])
app.include_router(services.router, prefix="/services", tags=["services"])

@app.get("/")
async def root():
    return {"message": "Repair Service API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
