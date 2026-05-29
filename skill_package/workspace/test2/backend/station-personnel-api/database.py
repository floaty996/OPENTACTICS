"""
数据库连接 —— 读源库 basic_data（只读），写目标库 allocation（可写）
"""
from __future__ import annotations

import os
import pymysql
from typing import Any

_CONFIG_CACHE: dict | None = None


def _load_config() -> dict:
    """读取 workspace config.json（绝对路径）"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE:
        return _CONFIG_CACHE

    import json
    config_path = os.environ.get("STUDIO_WORKSPACE_CONFIG")
    if config_path and os.path.isfile(config_path):
        with open(config_path) as f:
            cfg = json.load(f)
    else:
        # 兜底：从脚本相对路径推算
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent.parent.parent / "config.json"
        with open(p) as f:
            cfg = json.load(f)

    _CONFIG_CACHE = cfg
    return cfg


def _get_source_cfg() -> dict:
    """获取 basic_data 源库连接参数"""
    cfg = _load_config()
    src_list = cfg.get("source_databases", [])
    if not src_list:
        raise RuntimeError("config.json 未配置 source_databases")
    return {
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.get("port", 3306),
        "user": cfg.get("user", "root"),
        "password": cfg.get("password", ""),
        "database": "basic_data",
        "charset": "utf8mb4",
    }


def _get_target_cfg() -> dict:
    """获取 allocation 目标库连接参数"""
    cfg = _load_config()
    # 目标库密码可能单独配置
    pwd = os.environ.get("DB_TARGET_PASSWORD") or cfg.get("target_password") or cfg.get("password", "")
    return {
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.get("port", 3306),
        "user": cfg.get("target_user") or cfg.get("user", "root"),
        "password": pwd,
        "database": "allocation",
        "charset": "utf8mb4",
    }


def _source_conn():
    cfg = _get_source_cfg()
    return pymysql.connect(**cfg, cursorclass=pymysql.cursors.DictCursor)


def _target_conn():
    cfg = _get_target_cfg()
    return pymysql.connect(**cfg, cursorclass=pymysql.cursors.DictCursor)


# ─── 源库查询（只读） ───

def fetch_all_source(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    conn = _source_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_one_source(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    conn = _source_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


# ─── 目标库查询（可写） ───

def fetch_all_target(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    conn = _target_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_one_target(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    conn = _target_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def execute_target(sql: str, params: list[Any] | None = None) -> int:
    """执行 INSERT/UPDATE/DELETE 到 allocation 库，返回 lastrowid"""
    conn = _target_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            conn.commit()
            return cur.lastrowid or 0
    finally:
        conn.close()
