"""FastAPI application entry point."""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.routers import schedule

# 尝试导入数据库模块（如果可用）
try:
    from database.config import init_db, engine
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    if DB_AVAILABLE:
        try:
            init_db()
            print("Database initialized successfully")
        except Exception as e:
            print(f"Database initialization failed: {e}")
            print("Running without database support")
    yield
    # 关闭时清理资源


app = FastAPI(
    title="AIScheduling API",
    description="Backend API for the shift scheduling system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(schedule.router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "AIScheduling API", "db_available": DB_AVAILABLE}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "db_available": DB_AVAILABLE}
