"""Full-stack deliverable checks (read-only workspace, no writes)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skill_package.workspace.paths import backend_dir, frontend_dir, validate_db_alias

API_MANIFEST = "api_manifest.json"
UI_MANIFEST = "ui_manifest.json"
BACKEND_REQUIRED = ("main.py", "api_manifest.json", "requirements.txt")
BACKEND_RECOMMENDED = ("api_knowledge.md",)
FRONTEND_PREVIEW_CANDIDATES = ("preview.html", "index.html", "dist/index.html", "public/index.html")


def find_preview_entry(proj_dir: Path) -> str | None:
    for rel in FRONTEND_PREVIEW_CANDIDATES:
        if (proj_dir / rel).is_file():
            return rel
    return None


def _read_json_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _audit_studio_backend_compat(proj_dir: Path, meta: dict[str, Any]) -> list[str]:
    """Check backend against Skill Studio preview / backend_runner conventions."""
    gaps: list[str] = []
    prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
    if prefix and (not prefix.startswith("/") or " " in prefix or "（" in prefix or "）" in prefix):
        gaps.append(
            'api_manifest.api_prefix must be a path only (e.g. "/api" or ""), not prose'
        )
    if len(prefix) > 64:
        gaps.append("api_manifest.api_prefix is too long; keep a short path only")

    linked = str(meta.get("linked_frontend") or "").strip()
    if not linked:
        gaps.append("api_manifest.linked_frontend is required (Studio links backend to frontend)")

    port = meta.get("default_port")
    if port is not None:
        try:
            p = int(port)
            if p < 1024 or p > 65535:
                gaps.append("api_manifest.default_port must be between 1024 and 65535")
        except (TypeError, ValueError):
            gaps.append("api_manifest.default_port must be an integer (8000 recommended)")

    main_py = proj_dir / "main.py"
    if main_py.is_file():
        try:
            text = main_py.read_text(encoding="utf-8")
        except OSError:
            gaps.append("Cannot read main.py")
            text = ""
        if text:
            try:
                compile(text, str(main_py), "exec")
            except SyntaxError as e:
                gaps.append(f"main.py syntax error: {e.msg} (line {e.lineno})")
            uses_direct = "direct_router" in text
            defines_direct = "direct_router =" in text or "direct_router=" in text
            if uses_direct and not defines_direct:
                gaps.append("main.py uses direct_router but does not define it (direct_router = APIRouter())")
            if "app = FastAPI" not in text and "app=FastAPI" not in text:
                gaps.append("main.py must define app = FastAPI(...)")
            if "include_router" not in text:
                gaps.append("main.py must call app.include_router(...)")
            if re.search(r"from\s+\.", text) or re.search(r"from\s+\.\.", text):
                gaps.append(
                    "main.py uses relative imports (from . / from ..); "
                    "Studio runs uvicorn main:app — use absolute imports"
                )
            from skill_package.core.fullstack_contract import audit_backend_route_contract

            gaps.extend(audit_backend_route_contract(proj_dir, meta))
        for py_file in proj_dir.rglob("*.py"):
            if "_template" in py_file.parts or py_file.name.startswith("."):
                continue
            try:
                py_text = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if py_file != main_py and (
                re.search(r"from\s+\.", py_text) or re.search(r"from\s+\.\.", py_text)
            ):
                rel = py_file.relative_to(proj_dir).as_posix()
                gaps.append(f"{rel} uses relative imports; use absolute (e.g. from database import ...)")
                break
    else:
        gaps.append("Missing main.py (Studio cannot start uvicorn main:app)")

    req = proj_dir / "requirements.txt"
    if req.is_file():
        body = req.read_text(encoding="utf-8").lower()
        if "fastapi" not in body:
            gaps.append("requirements.txt must include fastapi")
        if "uvicorn" not in body:
            gaps.append("requirements.txt must include uvicorn")

    return gaps


def audit_backend_project(proj_dir: Path) -> dict[str, Any]:
    missing_required = [f for f in BACKEND_REQUIRED if not (proj_dir / f).is_file()]
    missing_recommended = [f for f in BACKEND_RECOMMENDED if not (proj_dir / f).is_file()]
    meta = _read_json_manifest(proj_dir / API_MANIFEST) or {}
    studio_gaps = _audit_studio_backend_compat(proj_dir, meta)
    linked = str(meta.get("linked_frontend") or "").strip()
    linked_path = None
    linked_exists = False
    if linked:
        fe_root = proj_dir.parent.parent / "frontend" / linked
        linked_path = f"frontend/{linked}"
        linked_exists = fe_root.is_dir() and (fe_root / UI_MANIFEST).is_file()
    ready_to_run = not missing_required and not studio_gaps
    return {
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "studio_gaps": studio_gaps,
        "ready_to_run": ready_to_run,
        "ready_for_studio": ready_to_run,
        "linked_frontend": linked or None,
        "linked_frontend_path": linked_path,
        "linked_frontend_exists": linked_exists if linked else None,
    }


def audit_frontend_project(proj_dir: Path, *, linked_backend_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    from skill_package.core.fullstack_contract import audit_frontend_studio_compat

    missing: list[str] = []
    if not (proj_dir / UI_MANIFEST).is_file():
        missing.append(UI_MANIFEST)
    preview = find_preview_entry(proj_dir)
    if not preview:
        missing.append("preview.html or index.html (required for Studio preview)")
    if not (proj_dir / "ui_knowledge.md").is_file():
        missing.append("ui_knowledge.md (recommended)")
    studio_gaps = audit_frontend_studio_compat(proj_dir, linked_backend_meta=linked_backend_meta)
    ready = bool(preview and (proj_dir / UI_MANIFEST).is_file() and not studio_gaps)
    return {
        "missing_required": missing,
        "preview_entry": preview,
        "has_preview": bool(preview),
        "studio_gaps": studio_gaps,
        "ready_for_studio": ready,
    }


def _scan_backend_rows(alias: str) -> list[dict[str, Any]]:
    root = backend_dir(alias)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for manifest_path in root.rglob(API_MANIFEST):
        if "_template" in manifest_path.parts:
            continue
        proj_dir = manifest_path.parent
        name = proj_dir.relative_to(root).as_posix()
        meta = _read_json_manifest(manifest_path) or {}
        if not meta.get("has_database_connection"):
            continue
        rows.append(
            {
                "project_name": name,
                "workspace_path": f"workspace/{alias}/backend/{name}",
                "linked_frontend": meta.get("linked_frontend"),
                "proj_dir": proj_dir,
            }
        )
    return sorted(rows, key=lambda r: r["project_name"])


def _scan_frontend_rows(alias: str) -> list[dict[str, Any]]:
    root = frontend_dir(alias)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for manifest_path in root.rglob(UI_MANIFEST):
        if "_template" in manifest_path.parts:
            continue
        proj_dir = manifest_path.parent
        name = proj_dir.relative_to(root).as_posix()
        meta = _read_json_manifest(manifest_path) or {}
        if not meta.get("has_database_connection"):
            continue
        rows.append(
            {
                "project_name": name,
                "workspace_path": f"workspace/{alias}/frontend/{name}",
                "proj_dir": proj_dir,
            }
        )
    return sorted(rows, key=lambda r: r["project_name"])


def verify_fullstack_status(db_alias: str) -> dict[str, Any]:
    """Summarize whether backend/frontend deliverables are complete (read-only)."""
    alias = validate_db_alias(db_alias)
    gaps: list[str] = []
    backends_out: list[dict[str, Any]] = []
    frontends_out: list[dict[str, Any]] = []

    for row in _scan_backend_rows(alias):
        proj_dir: Path = row.pop("proj_dir")
        audit = audit_backend_project(proj_dir)
        item = {**row, **audit}
        backends_out.append(item)
        if audit["missing_required"]:
            gaps.append(
                f"Backend {row['project_name']} missing required: {', '.join(audit['missing_required'])}"
            )
        if audit["missing_recommended"]:
            gaps.append(
                f"Backend {row['project_name']} recommended: {', '.join(audit['missing_recommended'])}"
            )
        for sg in audit.get("studio_gaps") or []:
            gaps.append(f"Backend {row['project_name']} Studio preview: {sg}")
        linked = audit.get("linked_frontend")
        if linked and not audit.get("linked_frontend_exists"):
            gaps.append(
                f"Backend {row['project_name']} linked_frontend={linked!r} missing on disk; "
                "create the frontend project via UI_build save_ui_file"
            )

    for row in _scan_frontend_rows(alias):
        proj_dir = row.pop("proj_dir")
        linked_be = next(
            (b for b in backends_out if b.get("linked_frontend") == row["project_name"]),
            None,
        )
        be_meta = None
        if linked_be:
            be_meta = _read_json_manifest(
                backend_dir(alias) / linked_be["project_name"] / API_MANIFEST
            )
        audit = audit_frontend_project(proj_dir, linked_backend_meta=be_meta)
        item = {**row, **audit}
        frontends_out.append(item)
        if audit["missing_required"]:
            gaps.append(
                f"Frontend {row['project_name']} missing: {', '.join(audit['missing_required'])}"
            )
        for sg in audit.get("studio_gaps") or []:
            gaps.append(f"Frontend {row['project_name']} Studio preview: {sg}")
        if linked_be:
            from skill_package.core.deliverables import find_preview_entry
            from skill_package.core.fullstack_contract import audit_fetch_paths_match_backend

            be_dir = backend_dir(alias) / linked_be["project_name"]
            preview = find_preview_entry(proj_dir)
            if preview and be_dir.is_dir():
                try:
                    html = (proj_dir / preview).read_text(encoding="utf-8")
                    for fg in audit_fetch_paths_match_backend(
                        html,
                        backend_proj_dir=be_dir,
                        linked_backend_meta=be_meta,
                    ):
                        gaps.append(f"Frontend {row['project_name']} route contract: {fg}")
                except OSError:
                    pass

    if not backends_out:
        gaps.append("No DB-connected backend (backend/*/api_manifest.json)")
    if not frontends_out:
        gaps.append("No DB-connected frontend (frontend/*/ui_manifest.json)")

    system_complete = (
        bool(backends_out)
        and bool(frontends_out)
        and not gaps
        and all(b.get("ready_for_studio") for b in backends_out)
        and all(f.get("ready_for_studio") for f in frontends_out)
    )

    return {
        "ok": True,
        "db_alias": alias,
        "system_complete": system_complete,
        "backends": backends_out,
        "frontends": frontends_out,
        "gaps": gaps,
        "message": (
            "Full-stack deliverables complete; safe to close out with the user."
            if system_complete
            else "Full-stack incomplete; follow gaps and use save_backend_file / save_ui_file. "
            "Do not claim the frontend or full stack is done."
        ),
    }
