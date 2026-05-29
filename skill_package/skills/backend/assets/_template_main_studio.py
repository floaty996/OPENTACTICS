"""
Skill Studio 兼容的 FastAPI 入口模板（复制到 backend/{project}/main.py 后按业务改写）。

Studio backend_runner 启动命令：uvicorn main:app --host 127.0.0.1 --port {default_port}
须保证本文件可被 import，且 app 对象存在。
"""
from __future__ import annotations

import os
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 单一路由前缀（推荐）：与 api_manifest.json 的 api_prefix="/api" 一致
api_router = APIRouter(prefix="/api")

# 若业务需要「无前缀」与「/api」双路径，须同时定义并注册 direct_router（勿只写装饰器不定义）
# direct_router = APIRouter()

app = FastAPI(title="API", version="1.0.0")

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


@api_router.get("/health")
def health():
    return {"ok": True}


# @api_router.get("/your-route") ...

app.include_router(api_router)
# 若使用 direct_router：app.include_router(direct_router)


def _studio_config_hint() -> str:
    """database.py 应优先读环境变量（Studio 预览已注入）。"""
    return os.environ.get("STUDIO_WORKSPACE_CONFIG", "")
