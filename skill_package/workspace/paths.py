"""统一工作区：skill_package/workspace/{db_alias}/"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PACKAGE_ROOT / "workspace"
TEMPLATES_ROOT = WORKSPACE_ROOT / "_templates"

_ALIAS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def validate_db_alias(db_alias: str) -> str:
    a = db_alias.strip()
    if not a or not _ALIAS_RE.match(a):
        raise ValueError("db_alias 须以字母开头，仅含字母、数字、下划线、连字符，最长 64。")
    return a


def workspace_dir(db_alias: str) -> Path:
    return (WORKSPACE_ROOT / validate_db_alias(db_alias)).resolve()


def dataset_dir(db_alias: str) -> Path:
    return workspace_dir(db_alias) / "dataset"


def data_dir(db_alias: str) -> Path:
    path = workspace_dir(db_alias) / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_files_dir(db_alias: str) -> Path:
    path = workspace_dir(db_alias) / "source_files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frontend_dir(db_alias: str) -> Path:
    return workspace_dir(db_alias) / "frontend"


def backend_dir(db_alias: str) -> Path:
    return workspace_dir(db_alias) / "backend"


def config_path(db_alias: str) -> Path:
    return workspace_dir(db_alias) / "config.json"


def manifest_path(db_alias: str) -> Path:
    return workspace_dir(db_alias) / "manifest.json"


def ensure_workspace(db_alias: str) -> Path:
    alias = validate_db_alias(db_alias)
    root = workspace_dir(alias)
    (root / "dataset").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "source_files").mkdir(parents=True, exist_ok=True)
    (root / "frontend").mkdir(parents=True, exist_ok=True)
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "conversations").mkdir(parents=True, exist_ok=True)
    mp = manifest_path(alias)
    if not mp.exists():
        default = {
            "db_alias": alias,
            "config": "config.json",
            "dataset": "dataset/",
            "source_files": "source_files/",
            "frontend": "frontend/",
            "backend": "backend/",
            "projects": [],
            "backend_projects": [],
            "knowledge_files": [],
            "updated_at": _now_iso(),
        }
        mp.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def list_workspace_aliases() -> list[str]:
    if not WORKSPACE_ROOT.is_dir():
        return []
    out: list[str] = []
    for p in sorted(WORKSPACE_ROOT.iterdir()):
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if _ALIAS_RE.match(p.name):
            out.append(p.name)
    return out


def read_manifest(db_alias: str) -> dict[str, Any]:
    mp = manifest_path(db_alias)
    if not mp.is_file():
        return {}
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def touch_manifest(db_alias: str, **patch: Any) -> None:
    """更新 manifest.json；不自动重建已删除的 dataset/frontend/backend 目录。"""
    alias = validate_db_alias(db_alias)
    root = workspace_dir(alias)
    root.mkdir(parents=True, exist_ok=True)
    (root / "conversations").mkdir(parents=True, exist_ok=True)
    data = read_manifest(db_alias)
    if not data:
        data = {
            "db_alias": validate_db_alias(db_alias),
            "config": "config.json",
            "dataset": "dataset/",
            "source_files": "source_files/",
            "frontend": "frontend/",
            "backend": "backend/",
            "projects": [],
            "backend_projects": [],
            "knowledge_files": [],
        }
    for key, val in patch.items():
        data[key] = val
    data["updated_at"] = _now_iso()
    manifest_path(db_alias).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
