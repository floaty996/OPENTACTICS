"""
站点人员信息系统 — FastAPI 入口
数据库：源库 basic_data（只读）+ 目标库 allocation（可写）
启动命令：uvicorn main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from routers.employees import router as employees_router
from routers.stations import router as stations_router
from routers.transfers import router as transfers_router

app = FastAPI(title="站点人员信息系统", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

@api_router.get("/health")
def health():
    return {"ok": True, "db": "mysql(basic_data + allocation)"}

app.include_router(api_router)
app.include_router(employees_router)
app.include_router(stations_router)
app.include_router(transfers_router)
