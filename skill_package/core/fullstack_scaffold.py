"""One-shot scaffold: runnable backend + frontend skeleton per full-stack rules."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from skill_package.core.fullstack_contract import generate_preview_api_block
from skill_package.workspace.paths import backend_dir, frontend_dir, validate_db_alias

_ASSETS = Path(__file__).resolve().parents[1] / "skills"
_BACKEND_TEMPLATE = _ASSETS / "backend" / "assets" / "_template_main_studio.py"
_UI_MANIFEST_TEMPLATE = _ASSETS / "UI_build" / "assets" / "_template_ui_manifest.json"
_PREVIEW_TEMPLATE = _ASSETS / "UI_build" / "assets" / "_template_preview_studio.html"

DEFAULT_REQUIREMENTS = """fastapi>=0.110.0
uvicorn[standard]>=0.27.0
"""

DATABASE_PY_STUB = '''"""Database access (prefer Studio-injected environment variables)."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def _sqlite_path() -> str:
    return os.environ.get("STUDIO_LOCAL_SQLITE") or str(Path("data") / "app.db")


def fetch_all(sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(_sqlite_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params or [])
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def fetch_one(sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
'''


def build_scaffold_plan(
    db_alias: str,
    *,
    frontend_project: str,
    backend_project: str | None = None,
    service_title: str = "API",
) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    fe_name = frontend_project.strip().strip("/")
    be_name = (backend_project or f"{fe_name}-api").strip().strip("/")
    if not fe_name or not be_name:
        raise ValueError("Invalid frontend_project or backend_project")

    main_py = _BACKEND_TEMPLATE.read_text(encoding="utf-8")
    main_py = main_py.replace('title="API"', f'title="{service_title}"')

    api_manifest = {
        "has_database_connection": True,
        "linked_frontend": fe_name,
        "default_port": 8000,
        "api_prefix": "/api",
        "stack": "fastapi",
        "description": service_title,
    }
    ui_manifest: dict[str, Any] = {
        "has_database_connection": True,
        "stack": "preview-html",
        "description": service_title,
    }
    if _UI_MANIFEST_TEMPLATE.is_file():
        try:
            ui_manifest = json.loads(_UI_MANIFEST_TEMPLATE.read_text(encoding="utf-8"))
            ui_manifest["has_database_connection"] = True
            ui_manifest["project_name"] = fe_name
            ui_manifest["db_alias"] = alias
        except (json.JSONDecodeError, OSError):
            pass

    preview_html = _PREVIEW_TEMPLATE.read_text(encoding="utf-8") if _PREVIEW_TEMPLATE.is_file() else ""
    if not preview_html:
        preview_html = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Preview</title></head>'
            '<body><p id="apiStatus">Loading…</p><script>\n'
            + generate_preview_api_block()
            + "\ncheckBackendHealth();\n</script></body></html>"
        )

    api_knowledge = f"""---
db_alias: "{alias}"
project_name: "{be_name}"
linked_frontend: "{fe_name}"
api_prefix: "/api"
default_port: 8000
---

# {service_title} — API knowledge

## REST endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |

## Frontend integration

- Frontend: `frontend/{fe_name}/`
- API base: `http://127.0.0.1:8000/api`
- preview uses `apiGet('/health')` etc. (paths without duplicate /api prefix)
"""

    ui_knowledge = f"""---
db_alias: "{alias}"
project_name: "{fe_name}"
linked_backend: "{be_name}"
---

# {service_title} — UI knowledge

## API integration

- Use `apiGet` / `apiPost` from the FULLSTACK_API block in preview.html
- Call `get_fullstack_api_contract` before business requests to read `route_fetch_map`
"""

    files: list[dict[str, str]] = [
        {"side": "backend", "project": be_name, "path": "api_manifest.json", "content": json.dumps(api_manifest, ensure_ascii=False, indent=2) + "\n"},
        {"side": "backend", "project": be_name, "path": "main.py", "content": main_py},
        {"side": "backend", "project": be_name, "path": "requirements.txt", "content": DEFAULT_REQUIREMENTS},
        {"side": "backend", "project": be_name, "path": "database.py", "content": DATABASE_PY_STUB},
        {"side": "backend", "project": be_name, "path": "routers/__init__.py", "content": ""},
        {"side": "backend", "project": be_name, "path": "api_knowledge.md", "content": api_knowledge},
        {"side": "frontend", "project": fe_name, "path": "ui_manifest.json", "content": json.dumps(ui_manifest, ensure_ascii=False, indent=2) + "\n"},
        {"side": "frontend", "project": fe_name, "path": "preview.html", "content": preview_html},
        {"side": "frontend", "project": fe_name, "path": "ui_knowledge.md", "content": ui_knowledge},
    ]

    return {
        "ok": True,
        "db_alias": alias,
        "frontend_project": fe_name,
        "backend_project": be_name,
        "files": files,
        "next_steps": [
            "Use save_backend_file for business routers (or patch main.py include_router)",
            f"get_fullstack_api_contract(db_alias={alias!r}, frontend_project={fe_name!r})",
            "Use save_ui_file to extend preview.html business UI",
            "Call verify_fullstack_deliverables before telling the user the system is complete",
        ],
        "spec": "skill_package/core/fullstack_enforce.py GENERATION_SPEC",
    }


def write_scaffold_to_workspace(plan: dict[str, Any]) -> dict[str, Any]:
    """Write scaffold plan to disk (scaffold_fullstack_project tool)."""
    alias = validate_db_alias(plan["db_alias"])
    written: list[str] = []
    for item in plan.get("files") or []:
        side = item["side"]
        proj = item["project"]
        rel = item["path"]
        content = item["content"]
        if side == "backend":
            root = backend_dir(alias) / proj
        else:
            root = frontend_dir(alias) / proj
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(f"{side}/{proj}/{rel}")
    return {"written": written, "count": len(written)}
