"""saas 本地持久化（无 MySQL 目标库时使用 SQLite）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from skill_package.workspace.paths import validate_db_alias, workspace_dir

DEFAULT_LOCAL_SQLITE_REL = "data/app.db"


def local_data_dir(db_alias: str) -> Path:
    alias = validate_db_alias(db_alias)
    path = workspace_dir(alias) / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_local_sqlite_path(db_alias: str, *, rel_path: str | None = None) -> Path:
    alias = validate_db_alias(db_alias)
    rel = (rel_path or DEFAULT_LOCAL_SQLITE_REL).strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError(f"非法 local_sqlite_path: {rel_path!r}")
    path = (workspace_dir(alias) / rel).resolve()
    root = workspace_dir(alias).resolve()
    if root not in path.parents and path != root / rel:
        if not str(path).startswith(str(root)):
            raise ValueError("local_sqlite_path 须位于 workspace 内")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_local_sqlite(db_alias: str, *, rel_path: str | None = None) -> Path:
    """确保本地 SQLite 文件存在（空库）。"""
    path = resolve_local_sqlite_path(db_alias, rel_path=rel_path)
    if not path.is_file():
        conn = sqlite3.connect(str(path))
        conn.close()
    return path


def resolve_storage_mode(cfg: dict) -> str:
    mode = str(cfg.get("storage_mode") or "").strip().lower()
    target = str(cfg.get("target_database") or "").strip()
    if mode in ("local", "mysql"):
        if mode == "mysql" and not target:
            return "local"
        return mode
    return "mysql" if target else "local"


def uses_mysql_target(cfg: dict) -> bool:
    return resolve_storage_mode(cfg) == "mysql"


def uses_mysql_sources(cfg: dict) -> bool:
    sources = cfg.get("source_databases") or []
    return bool(sources)
