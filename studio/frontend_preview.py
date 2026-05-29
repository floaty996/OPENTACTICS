"""Studio 内静态预览 workspace 前端工程 HTML。"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from skill_package.skills.UI_build.scripts.ui_assets import find_preview_entry, _project_root
from skill_package.workspace.paths import frontend_dir, validate_db_alias

_PREVIEW_MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ico": "image/x-icon",
}


def _validate_project_name(project_name: str) -> str:
    name = project_name.strip().strip("/")
    if not name or ".." in Path(name).parts:
        raise ValueError("project_name 非法")
    return name


def list_frontend_projects(db_alias: str) -> list[dict]:
    alias = validate_db_alias(db_alias)
    root = frontend_dir(alias)
    if not root.is_dir():
        return []
    rows: list[dict] = []
    for manifest in root.rglob("ui_manifest.json"):
        if manifest.name.startswith("_template"):
            continue
        proj_dir = manifest.parent
        project_name = proj_dir.relative_to(root).as_posix()
        entry = find_preview_entry(proj_dir)
        rows.append(
            {
                "project_name": project_name,
                "preview_entry": entry,
                "has_preview": bool(entry),
                "has_ui_knowledge": (proj_dir / "ui_knowledge.md").is_file(),
                "preview_url": f"/api/frontend-preview/{project_name}/" if entry else None,
            }
        )
    return sorted(rows, key=lambda r: r["project_name"])


def resolve_preview_file(db_alias: str, project_name: str, file_path: str | None) -> Path:
    alias = validate_db_alias(db_alias)
    proj_name = _validate_project_name(project_name)
    proj = _project_root(alias, proj_name)
    if not proj.is_dir():
        raise FileNotFoundError(f"前端工程不存在: {proj_name}")

    rel = (file_path or "").strip().lstrip("/")
    if not rel:
        entry = find_preview_entry(proj)
        if not entry:
            raise FileNotFoundError("该工程没有可预览的 HTML（需要 preview.html 或 index.html）")
        rel = entry

    if ".." in Path(rel).parts:
        raise ValueError("path 非法")

    target = (proj / rel).resolve()
    target.relative_to(proj.resolve())
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在: {rel}")
    return target


def guess_media_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _PREVIEW_MIME:
        return _PREVIEW_MIME[ext]
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"
