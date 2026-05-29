"""数据库连接配置 - 优先从环境变量获取密码，回退到 config.json"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pymysql

_API_DIR = Path(__file__).resolve().parent


def _resolve_config_path() -> Path:
    env_path = os.environ.get("STUDIO_WORKSPACE_CONFIG", "").strip()
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_file():
            return p
    candidates = [
        _API_DIR / ".." / ".." / "config.json",
        _API_DIR / "config.json",
    ]
    for c in candidates:
        resolved = c.resolve()
        if resolved.is_file():
            return resolved
    tried = ", ".join(str(c.resolve()) for c in candidates)
    raise FileNotFoundError(
        f"未找到工作区 config.json（已尝试: {tried}）。"
        "请在 Skill Studio 完成数据库配置，或设置环境变量 STUDIO_WORKSPACE_CONFIG。"
    )


def get_db_config():
    path = _resolve_config_path()
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    sources = cfg.get("source_databases") or []
    if not sources:
        raise ValueError(f"config.json 缺少 source_databases: {path}")

    # 密码优先级：环境变量 > config.json（config.json 中的密码可能被脱敏为 ***）
    db_password = os.environ.get("DB_PASSWORD", "").strip()
    if not db_password or db_password == "***":
        raw = cfg.get("password", "")
        # 如果 config.json 里的密码是 ***，说明被工具脱敏了，必须用环境变量
        if raw == "***":
            raise ValueError(
                "config.json 中的 password 已被脱敏为 '***'，无法使用。\n"
                "请通过环境变量 DB_PASSWORD 传入真实密码启动：\n"
                "  DB_PASSWORD='你的密码' uvicorn main:app --reload --port 8000"
            )
        db_password = raw

    return {
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"],
        "password": db_password,
        "database": sources[0],
        "charset": "utf8mb4",
    }


def get_connection():
    cfg = get_db_config()
    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset=cfg["charset"],
        cursorclass=pymysql.cursors.DictCursor,
    )
