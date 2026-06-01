"""Full-stack generation hard rules: pre-write validation; failures block save (runnable + integrated)."""

from __future__ import annotations

import json
import re
from typing import Any

SPEC_VERSION = "1.0"

GENERATION_SPEC: dict[str, Any] = {
    "version": SPEC_VERSION,
    "priority": "runnable > feature-complete > polish",
    "mandatory_order": [
        "database (schema / dataset)",
        "scaffold_fullstack_project or template-based backend + frontend",
        "backend: routers + api_knowledge.md",
        "get_fullstack_api_contract",
        "UI_build: preview.html business logic (apiGet/apiPost only)",
        "verify_fullstack_deliverables (system_complete must be true)",
    ],
    "backend_rules": [
        'api_manifest.api_prefix must be "/api"',
        "api_manifest.linked_frontend required (frontend directory name)",
        "main.py must define app = FastAPI and app.include_router",
        'Routes use APIRouter(prefix="/api/...") or api_router(prefix="/api")',
        "No add_api_route unprefixed business routes (no dual-path shim)",
        "No relative imports (from . / from ..) in any .py",
        'GET /api/health must return {"ok": true}',
        "requirements.txt must include fastapi and uvicorn",
    ],
    "frontend_rules": [
        "preview.html and ui_manifest.json required",
        "No const API or hardcoded http://127.0.0.1:8xxx",
        "Data calls only via apiGet/apiPost/apiPut/apiDel (FULLSTACK_API block)",
        "apiGet paths must appear in get_fullstack_api_contract.route_fetch_map",
        'When api_prefix is /api, paths must not start with "/api/"',
    ],
    "completion_gate": "verify_fullstack_deliverables.system_complete === true",
}

_REL_IMPORT = re.compile(r"^\s*from\s+(\.+)([\w.]*)\s*import\s+", re.M)
_HARDCODED_API = re.compile(r"https?://(?:127\.0\.0\.1|localhost):80\d{2}", re.I)
_API_VAR = re.compile(r"(?:var|const|let)\s+API\s*=", re.I)
_DUAL_ROUTE = re.compile(r'add_api_route\s*\(\s*["\']/(?!api/)', re.I)
_ROOT_HEALTH = re.compile(r'@app\.get\s*\(\s*["\']/health["\']', re.I)


def spec_summary_text() -> str:
    lines = [f"Full-stack generation spec v{SPEC_VERSION} (mandatory)", ""]
    for i, step in enumerate(GENERATION_SPEC["mandatory_order"], 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("Backend: " + "; ".join(GENERATION_SPEC["backend_rules"][:4]) + "…")
    lines.append("Completion: " + GENERATION_SPEC["completion_gate"])
    return "\n".join(lines)


def validate_api_manifest_content(content: str) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return [f"api_manifest.json is not valid JSON: {e}"]
    if not isinstance(data, dict):
        return ["api_manifest.json must be a JSON object"]
    if not data.get("has_database_connection"):
        errors.append("has_database_connection must be true")
    prefix = str(data.get("api_prefix") if data.get("api_prefix") is not None else "")
    if prefix != "/api":
        errors.append('api_prefix must be "/api" (no other values in full-stack spec)')
    if not str(data.get("linked_frontend") or "").strip():
        errors.append("linked_frontend is required (frontend project directory name)")
    if "（" in prefix or "）" in prefix or " " in prefix:
        errors.append("api_prefix must be a path only (no prose or spaces)")
    port = data.get("default_port", 8000)
    try:
        if not (1024 <= int(port) <= 65535):
            errors.append("default_port must be between 1024 and 65535")
    except (TypeError, ValueError):
        errors.append("default_port must be an integer")
    return errors


def validate_backend_python(rel_path: str, content: str) -> list[str]:
    errors: list[str] = []
    if _REL_IMPORT.search(content):
        errors.append(
            f"{rel_path} uses relative imports; use absolute imports "
            "(e.g. from routers import xxx, from database import xxx)"
        )
    if rel_path == "main.py":
        if "app = FastAPI" not in content and "app=FastAPI" not in content:
            errors.append("main.py must define app = FastAPI(...)")
        if "include_router" not in content:
            errors.append("main.py must call app.include_router(...)")
        if _DUAL_ROUTE.search(content):
            errors.append(
                "main.py must not add_api_route unprefixed business routes; use /api prefix only"
            )
        if _ROOT_HEALTH.search(content) and (
            'prefix="/api"' in content or "prefix='/api'" in content
        ):
            errors.append(
                'main.py must not use @app.get("/health") alongside /api routes; '
                'use @api_router.get("/health") only'
            )
        try:
            compile(content, rel_path, "exec")
        except SyntaxError as e:
            errors.append(f"main.py syntax error: {e.msg} (line {e.lineno})")
    return errors


def validate_preview_html(content: str) -> list[str]:
    """Block preview patterns that break backend integration."""
    errors: list[str] = []
    if _API_VAR.search(content):
        errors.append("Do not declare const API; use apiGet/apiPost from FULLSTACK_API block")
    if _HARDCODED_API.search(content):
        errors.append("Do not hardcode 127.0.0.1:8xxx; API_BASE is managed by FULLSTACK_API block")
    if re.search(r"(?:fetch|apiGet|apiPost)\s*\(\s*['\"]/api/", content, re.I):
        errors.append('When api_prefix is /api, apiGet paths must not start with "/api/"')
    return errors


def validate_requirements_content(content: str) -> list[str]:
    body = content.lower()
    errors: list[str] = []
    if "fastapi" not in body:
        errors.append("requirements.txt must include fastapi")
    if "uvicorn" not in body:
        errors.append("requirements.txt must include uvicorn")
    return errors


def blocking_errors_for_backend_file(
    rel_path: str,
    content: str,
    *,
    after_autofix: bool = False,
) -> list[str]:
    rel = rel_path.strip().lstrip("/")
    if rel == API_MANIFEST_NAME:
        return validate_api_manifest_content(content)
    if rel == "requirements.txt":
        return validate_requirements_content(content)
    if rel.endswith(".py"):
        return validate_backend_python(rel, content)
    return []


API_MANIFEST_NAME = "api_manifest.json"
