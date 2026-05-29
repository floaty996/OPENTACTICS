"""
员工民族分析 API - FastAPI 主入口
包含后台健康检查任务（每 60 秒自动检查数据库连接）
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routers import ethnic_analysis

# ---- 全局状态 ----
app_state: dict = {
    "healthy": False,
    "last_check": None,
    "error": None,
    "uptime": None,
}


def check_db_health() -> Optional[str]:
    """尝试连接数据库并执行简单查询，成功返回 None，失败返回错误信息"""
    try:
        from db import get_connection
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS alive")
                cur.fetchone()
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


async def health_check_loop(interval_sec: int = 60):
    """后台定期健康检查循环"""
    while True:
        err = await asyncio.to_thread(check_db_health)
        app_state["healthy"] = err is None
        app_state["last_check"] = datetime.now(timezone.utc).isoformat()
        app_state["error"] = err
        await asyncio.sleep(interval_sec)


# ---- FastAPI 应用 ----
app = FastAPI(
    title="员工民族分析 API",
    description="对接 basic_data 库 metro_employees 表，提供民族构成、分布等统计分析",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ethnic_analysis.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """确保 500 仍返回 JSON，以便 CORS 中间件附加头（避免浏览器报 Failed to fetch）。"""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error": type(exc).__name__},
    )

@app.on_event("startup")
async def startup():
    """应用启动时：记录启动时间、初始化健康检查状态、启动后台任务"""
    app_state["uptime"] = datetime.now(timezone.utc).isoformat()
    # 首次立即检查
    err = await asyncio.to_thread(check_db_health)
    app_state["healthy"] = err is None
    app_state["last_check"] = datetime.now(timezone.utc).isoformat()
    app_state["error"] = err
    # 启动定期检查任务
    asyncio.create_task(health_check_loop(interval_sec=60))
    status = "✅ 数据库连接正常" if app_state["healthy"] else f"⚠️ 数据库连接异常: {err}"
    print(f"[startup] 健康检查完成，状态: {status}")


@app.get("/api/health")
async def health():
    """
    健康检查接口（含数据库存活性验证）
    返回服务状态 + 最近一次数据库检查结果
    """
    return {
        "status": "ok" if app_state["healthy"] else "degraded",
        "service": "ethnic-analysis-api",
        "uptime": app_state["uptime"],
        "database": {
            "healthy": app_state["healthy"],
            "last_check": app_state["last_check"],
            "error": app_state["error"],
        },
    }

