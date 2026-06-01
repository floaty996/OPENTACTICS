from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.UI_build.paths import UI_MANIFEST_NAME
from skill_package.workspace.file_patch import patch_text_file
from skill_package.workspace.paths import (
    backend_dir,
    frontend_dir,
    list_workspace_aliases,
    read_manifest,
    touch_manifest,
    validate_db_alias,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_ui_assets",
        "description": "List frontend projects under workspace/frontend/ (optional db_alias filter)",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "Omit to list all workspaces"},
            },
            "required": [],
        },
    },
}

check_schema = {
    "type": "function",
    "function": {
        "name": "check_db_connected_frontend",
        "description": (
            "Check whether workspace/{db_alias}/frontend/ has a DB-connected frontend; "
            "returns deliverables (e.g. missing preview.html). Call verify_fullstack_deliverables before closing."
        ),
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}

read_schema = {
    "type": "function",
    "function": {
        "name": "read_ui_asset",
        "description": "Read a file under workspace/{db_alias}/frontend/{project_name}/",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string", "description": "Project directory, e.g. admin-web"},
                "file_path": {"type": "string", "description": "Path inside project, e.g. src/App.tsx"},
            },
            "required": ["db_alias", "project_name", "file_path"],
        },
    },
}

save_schema = {
    "type": "function",
    "function": {
        "name": "save_ui_file",
        "description": (
            "Write a full file to the frontend project; use for new/large changes. "
            "Prefer patch_ui_file for small HTML/JS/CSS edits. content must be complete."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "Workspace alias (current saas)"},
                "project_name": {"type": "string", "description": "Directory under frontend/"},
                "file_path": {"type": "string", "description": "Relative path, e.g. preview.html"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["db_alias", "project_name", "file_path", "content"],
        },
    },
}

patch_schema = {
    "type": "function",
    "function": {
        "name": "patch_ui_file",
        "description": (
            "Patch an existing frontend file (old_string → new_string). "
            "Read the file first and copy exact text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
                "occurrence": {"type": "integer"},
            },
            "required": ["db_alias", "project_name", "file_path", "old_string", "new_string"],
        },
    },
}


def _project_root(db_alias: str, project_name: str) -> Path:
    alias = validate_db_alias(db_alias)
    name = project_name.strip().strip("/")
    if not name or ".." in Path(name).parts:
        raise ValueError("Invalid project_name")
    root = (frontend_dir(alias) / name).resolve()
    root.relative_to(frontend_dir(alias).resolve())
    return root


def _resolve_file(db_alias: str, project_name: str, file_path: str) -> Path:
    proj = _project_root(db_alias, project_name)
    rel = file_path.strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise ValueError("Invalid file_path")
    target = (proj / rel).resolve()
    target.relative_to(proj)
    return target


def _read_manifest_file(proj_dir: Path) -> dict | None:
    mp = proj_dir / UI_MANIFEST_NAME
    if not mp.is_file():
        return None
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _scan_projects(db_alias: str | None = None) -> list[dict]:
    aliases = [validate_db_alias(db_alias)] if db_alias and db_alias.strip() else list_workspace_aliases()
    rows: list[dict] = []
    for alias in aliases:
        root = frontend_dir(alias)
        if not root.is_dir():
            continue
        for manifest_path in root.rglob(UI_MANIFEST_NAME):
            if manifest_path.name.startswith("_template"):
                continue
            proj_dir = manifest_path.parent
            project_name = proj_dir.relative_to(root).as_posix()
            meta = _read_manifest_file(proj_dir) or {}
            rows.append(
                {
                    "db_alias": alias,
                    "project_name": project_name,
                    "workspace_path": f"workspace/{alias}/frontend/{project_name}",
                    "has_database_connection": bool(meta.get("has_database_connection")),
                    "stack": meta.get("stack"),
                }
            )
    return sorted(rows, key=lambda r: (r["db_alias"], r["project_name"]))


def find_preview_entry(proj_dir: Path) -> str | None:
    """Return relative HTML path usable for Studio static preview."""
    for rel in ("preview.html", "index.html", "dist/index.html", "public/index.html"):
        if (proj_dir / rel).is_file():
            return rel
    return None


def _after_ui_file_write(db_alias: str, project_name: str, file_path: str, target: Path) -> dict:
    alias = validate_db_alias(db_alias)
    proj = _project_root(alias, project_name)
    if file_path.strip().endswith(UI_MANIFEST_NAME) or (proj / UI_MANIFEST_NAME).exists():
        meta = _read_manifest_file(proj)
        _sync_project_manifest(alias, project_name, meta)
    elif file_path.strip().endswith((".html", ".htm")):
        _sync_project_manifest(alias, project_name, _read_manifest_file(proj))
    extra: dict = {}
    preview = find_preview_entry(proj)
    if preview:
        extra["preview_entry"] = preview
        extra["studio_preview_hint"] = (
            f"Open in Skill Studio System Preview: frontend/{project_name}/{preview}"
        )
    if file_path.strip().endswith((".html", ".htm")):
        from skill_package.core.deliverables import audit_frontend_project
        from skill_package.core.fullstack_contract import (
            build_api_contract,
            ensure_preview_api_block,
        )
        from skill_package.skills.backend.scripts.backend_assets import (
            _read_manifest_file as read_be_manifest,
            _scan_projects as scan_be,
        )

        linked_meta = None
        for row in scan_be(alias):
            if row.get("linked_frontend") == project_name:
                be_dir = backend_dir(alias) / row["project_name"]
                linked_meta = read_be_manifest(be_dir)
                break
        try:
            contract = build_api_contract(alias, frontend_project=project_name)
            raw = target.read_text(encoding="utf-8")
            merged, inject_changes = ensure_preview_api_block(raw, contract)
            if merged != raw:
                target.write_text(merged, encoding="utf-8")
                extra["fullstack_api_injected"] = inject_changes
            extra["api_contract"] = {
                "api_base_url": contract.get("api_base_url"),
                "backend_routes": contract.get("backend_routes"),
                "fetch_path_rule": contract.get("fetch_path_rule"),
            }
            if contract.get("gaps"):
                extra["contract_gaps"] = contract["gaps"]
            audit = audit_frontend_project(proj, linked_backend_meta=linked_meta)
            if audit.get("studio_gaps"):
                extra["studio_gaps"] = audit["studio_gaps"]
                extra["must_fix_before_complete"] = (
                    "preview.html failed full-stack contract; do not claim frontend/backend are linked: "
                    + "；".join(audit["studio_gaps"])
                )
        except ValueError as e:
            extra["api_contract_warning"] = str(e)
            extra["must_call"] = (
                "Backend not ready or linked_frontend missing; finish backend API first, "
                "then get_fullstack_api_contract and rewrite preview.html"
            )
        except OSError:
            pass
    return extra


def _sync_project_manifest(db_alias: str, project_name: str, meta: dict | None) -> None:
    proj_dir = _project_root(db_alias, project_name)
    manifest = read_manifest(db_alias)
    projects: list[dict] = list(manifest.get("projects") or [])
    entry = {
        "name": project_name,
        "path": f"frontend/{project_name}",
        "has_database_connection": bool((meta or {}).get("has_database_connection")),
        "has_ui_knowledge": (proj_dir / "ui_knowledge.md").is_file(),
        "preview_entry": find_preview_entry(proj_dir),
    }
    projects = [p for p in projects if p.get("name") != project_name]
    projects.append(entry)
    touch_manifest(db_alias, projects=projects)


preview_schema = {
    "type": "function",
    "function": {
        "name": "get_frontend_preview",
        "description": (
            "Get static preview entry (HTML path) for a frontend project in Skill Studio. "
            "Provide preview.html or index.html for full-page preview."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
            },
            "required": ["db_alias", "project_name"],
        },
    },
}

contract_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_api_contract",
        "description": (
            "[Required before writing preview.html] Return full-stack API contract: api_base_url, "
            "backend_routes, preview_api_block. save_ui_file auto-injects the block; use backend_routes "
            "for fetches; no custom const API or hardcoded ports."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {
                    "type": "string",
                    "description": "Frontend project name; matches backend linked_frontend",
                },
                "backend_project": {
                    "type": "string",
                    "description": "Optional; auto-resolved from linked_frontend when omitted",
                },
            },
            "required": ["db_alias"],
        },
    },
}


@register_skill_tool("UI_build", name="list_ui_assets", schema=list_schema)
def list_ui_assets(db_alias: str | None = None) -> str:
    projects = _scan_projects(db_alias)
    return json.dumps({"ok": True, "projects": projects, "count": len(projects)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="check_db_connected_frontend", schema=check_schema)
def check_db_connected_frontend(db_alias: str) -> str:
    from skill_package.core.deliverables import audit_frontend_project

    alias = validate_db_alias(db_alias)
    for row in _scan_projects(alias):
        if row.get("has_database_connection"):
            proj_dir = frontend_dir(alias) / row["project_name"]
            meta = _read_manifest_file(proj_dir)
            deliverables = audit_frontend_project(proj_dir)
            msg = "DB-connected frontend exists; iterate on it."
            if deliverables["missing_required"]:
                msg += (
                    f" Warning: missing {deliverables['missing_required']}; "
                    "use save_ui_file to add preview.html before Studio preview."
                )
            return json.dumps(
                {
                    "ok": True,
                    "exists": True,
                    "db_alias": alias,
                    "project_name": row["project_name"],
                    "workspace_path": row["workspace_path"],
                    "manifest": meta,
                    "deliverables": deliverables,
                    "message": msg,
                },
                ensure_ascii=False,
            )
    return json.dumps(
        {
            "ok": True,
            "exists": False,
            "db_alias": alias,
            "workspace_frontend": f"workspace/{alias}/frontend/",
            "message": (
                "No DB-connected frontend found; create under frontend/ with ui_manifest.json "
                "and save_ui_file for preview.html—do not claim frontend is done in prose only."
            ),
        },
        ensure_ascii=False,
    )


@register_skill_tool("UI_build", name="read_ui_asset", schema=read_schema)
def read_ui_asset(db_alias: str, project_name: str, file_path: str) -> str:
    try:
        target = _resolve_file(db_alias, project_name, file_path)
        if not target.exists():
            return json.dumps({"ok": False, "error": f"File not found: {target}"}, ensure_ascii=False)
        content = target.read_text(encoding="utf-8")
        if len(content) > 80000:
            content = content[:80000] + "\n...[TRUNCATED]"
        return json.dumps(
            {
                "ok": True,
                "db_alias": validate_db_alias(db_alias),
                "project_name": project_name,
                "file_path": file_path,
                "content": content,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="save_ui_file", schema=save_schema)
def save_ui_file(db_alias: str, project_name: str, file_path: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        rel = file_path.strip().lstrip("/")
        if rel.endswith((".html", ".htm")):
            from skill_package.core.fullstack_enforce import validate_preview_html, spec_summary_text

            violations = validate_preview_html(content)
            if violations:
                return json.dumps(
                    {
                        "ok": False,
                        "blocked": True,
                        "violations": violations,
                        "spec_summary": spec_summary_text(),
                        "message": "Violates full-stack frontend rules; preview write rejected. Remove const API / hardcoded ports.",
                    },
                    ensure_ascii=False,
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        extra = _after_ui_file_write(alias, project_name, file_path, target)
        payload: dict = {
            "ok": True,
            "db_alias": alias,
            "project_name": project_name,
            "path": str(target),
            "workspace_path": f"workspace/{alias}/frontend/{project_name}/{file_path.lstrip('/')}",
            "bytes": target.stat().st_size,
            "mode": "full_write",
            **extra,
        }
        if extra.get("studio_gaps"):
            payload["ok"] = False
            payload["blocked"] = True
            payload["violations"] = extra["studio_gaps"]
            payload["message"] = extra.get("must_fix_before_complete") or "preview failed full-stack contract check"
        return json.dumps(payload, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="patch_ui_file", schema=patch_schema)
def patch_ui_file(
    db_alias: str,
    project_name: str,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    occurrence: int = 1,
) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        patch_meta = patch_text_file(
            target,
            old_string,
            new_string,
            replace_all=bool(replace_all),
            occurrence=int(occurrence or 1),
        )
        extra = _after_ui_file_write(alias, project_name, file_path, target)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{file_path.lstrip('/')}",
                "mode": "patch",
                **patch_meta,
                **extra,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="get_fullstack_api_contract", schema=contract_schema)
def get_fullstack_api_contract_ui(
    db_alias: str,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> str:
    from skill_package.core.fullstack_contract import build_api_contract

    try:
        return json.dumps(
            build_api_contract(
                db_alias,
                frontend_project=frontend_project,
                backend_project=backend_project,
            ),
            ensure_ascii=False,
        )
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="get_frontend_preview", schema=preview_schema)
def get_frontend_preview(db_alias: str, project_name: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir():
            return json.dumps(
                {"ok": False, "error": f"Project not found: frontend/{project_name}/"},
                ensure_ascii=False,
            )
        entry = find_preview_entry(proj)
        if not entry:
            return json.dumps(
                {
                    "ok": True,
                    "has_preview": False,
                    "db_alias": alias,
                    "project_name": project_name,
                    "message": "No preview.html / index.html found; create a standalone preview.html for Studio.",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "has_preview": True,
                "db_alias": alias,
                "project_name": project_name,
                "preview_entry": entry,
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{entry}",
                "studio_preview_hint": "User can open Preview on the Skill Studio artifacts page for full-page view.",
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
