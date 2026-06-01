"""读取 workspace/{db_alias}/config.json 中的数据库配置。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_package.workspace.local_store import (
    DEFAULT_LOCAL_SQLITE_REL,
    ensure_local_sqlite,
    resolve_storage_mode,
)
from skill_package.workspace.paths import config_path, validate_db_alias
from skill_package.workspace.source_files_store import list_source_files


def _normalize_db_name(name: str) -> str:
    n = name.strip()
    if not n:
        raise ValueError("数据库名不能为空。")
    if not Path(n).name == n or ".." in n or "/" in n or "\\" in n:
        raise ValueError(f"非法数据库名: {name!r}")
    return n


def parse_database_list(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        names = [str(x).strip() for x in raw if str(x).strip()]
    else:
        names = [p.strip() for p in str(raw).replace("，", ",").split(",") if p.strip()]
    return [_normalize_db_name(n) for n in names]


def load_workspace_config(db_alias: str) -> dict[str, Any]:
    """加载工作区 config.json（源库/目标库均可为空，此时为本地 SQLite 模式）。"""
    alias = validate_db_alias(db_alias)
    path = config_path(alias)
    if not path.is_file():
        raise FileNotFoundError(f"未找到配置: {path}，请先 save_database_config 或在 Studio 完成初始化")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"config.json 格式错误: {path}")

    if "source_databases" not in data and data.get("database"):
        data["source_databases"] = [data["database"]]

    sources = parse_database_list(data.get("source_databases"))
    target_raw = data.get("target_database")
    target_db = _normalize_db_name(str(target_raw)) if target_raw and str(target_raw).strip() else ""

    if target_db and target_db in sources:
        raise ValueError("target_database 不能与 source_databases 中的库重名")

    storage_mode = resolve_storage_mode({**data, "target_database": target_db})
    data["storage_mode"] = storage_mode
    data["source_databases"] = sources
    data["target_database"] = target_db

    if storage_mode == "local":
        rel = str(data.get("local_sqlite_path") or DEFAULT_LOCAL_SQLITE_REL).strip()
        data["local_sqlite_path"] = rel
        data["file_path"] = rel
        ensure_local_sqlite(alias, rel_path=rel)
    elif not target_db:
        raise ValueError("mysql 模式须配置 target_database")

    data["source_files"] = list_source_files(alias, verify_disk=True)
    return data


def load_workspace_db_config(db_alias: str) -> dict[str, Any]:
    """兼容旧调用方。"""
    return load_workspace_config(db_alias)


def is_redacted_secret(value: Any) -> bool:
    """工具返回给模型时的脱敏占位，不能当作真实密码写回磁盘。"""
    s = str(value or "").strip()
    return not s or s == "***"


def merge_preserved_secrets(payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    """保存配置时：若新 payload 未提供真实密码，保留磁盘上已有密码。"""
    if not existing:
        return payload
    out = dict(payload)
    for key in ("password", "target_password", "gemini_api_key"):
        if is_redacted_secret(out.get(key)):
            prev = existing.get(key)
            if prev and not is_redacted_secret(prev):
                out[key] = prev
    return out


def mask_config_secrets(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key in ("password", "target_password", "gemini_api_key"):
        if out.get(key):
            out[key] = "***"
    return out
