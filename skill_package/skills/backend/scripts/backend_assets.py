from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.backend.paths import API_MANIFEST_NAME
from skill_package.workspace.file_patch import patch_text_file
from skill_package.workspace.paths import (
    backend_dir,
    list_workspace_aliases,
    read_manifest,
    touch_manifest,
    validate_db_alias,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_backend_projects",
        "description": "List backend API projects under workspace/backend/ (optional db_alias filter)",
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
        "name": "check_db_connected_backend",
        "description": (
            "Check whether workspace/{db_alias}/backend/ already has a DB-connected backend; "
            "returns deliverables (e.g. missing main.py). Call verify_fullstack_deliverables before closing full-stack work."
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
        "name": "read_backend_file",
        "description": "Read a file under workspace/{db_alias}/backend/{project_name}/",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string", "description": "Project directory name, e.g. ethnic-analysis-api"},
                "file_path": {"type": "string", "description": "Path inside project, e.g. main.py or routers/employees.py"},
            },
            "required": ["db_alias", "project_name", "file_path"],
        },
    },
}

save_schema = {
    "type": "function",
    "function": {
        "name": "save_backend_file",
        "description": (
            "Write a full file under workspace/{db_alias}/backend/{project_name}/. "
            "Use for new files or large rewrites; prefer patch_backend_file for small edits. "
            "content must be complete. New DB-connected backends need api_manifest.json first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "Workspace alias"},
                "project_name": {"type": "string", "description": "Directory under backend/"},
                "file_path": {"type": "string", "description": "Relative path inside project"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["db_alias", "project_name", "file_path", "content"],
        },
    },
}

patch_schema = {
    "type": "function",
    "function": {
        "name": "patch_backend_file",
        "description": (
            "Patch an existing backend file (old_string → new_string). "
            "Faster than save_backend_file. Read the file first and copy exact text. "
            "Use occurrence or replace_all when multiple matches exist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "file_path": {"type": "string"},
                "old_string": {
                    "type": "string",
                    "description": "Exact substring to replace; must match file content",
                },
                "new_string": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "If true, replace all matches; default false requires a unique match",
                },
                "occurrence": {
                    "type": "integer",
                    "description": "When replace_all=false and multiple matches, which match to replace (1-based)",
                },
            },
            "required": ["db_alias", "project_name", "file_path", "old_string", "new_string"],
        },
    },
}

run_info_schema = {
    "type": "function",
    "function": {
        "name": "get_backend_run_info",
        "description": (
            "Get local run commands, default port, API prefix, and linked frontend; "
            "returns studio_run_command / studio_gaps / ready_for_studio for Skill Studio preview checks."
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


def _project_root(db_alias: str, project_name: str) -> Path:
    alias = validate_db_alias(db_alias)
    name = project_name.strip().strip("/")
    if not name or ".." in Path(name).parts:
        raise ValueError("Invalid project_name")
    root = (backend_dir(alias) / name).resolve()
    root.relative_to(backend_dir(alias).resolve())
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
    mp = proj_dir / API_MANIFEST_NAME
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
        root = backend_dir(alias)
        if not root.is_dir():
            continue
        for manifest_path in root.rglob(API_MANIFEST_NAME):
            if manifest_path.name.startswith("_template"):
                continue
            proj_dir = manifest_path.parent
            project_name = proj_dir.relative_to(root).as_posix()
            meta = _read_manifest_file(proj_dir) or {}
            rows.append(
                {
                    "db_alias": alias,
                    "project_name": project_name,
                    "workspace_path": f"workspace/{alias}/backend/{project_name}",
                    "has_database_connection": bool(meta.get("has_database_connection")),
                    "stack": meta.get("stack"),
                    "linked_frontend": meta.get("linked_frontend"),
                    "default_port": meta.get("default_port"),
                    "api_prefix": meta.get("api_prefix"),
                }
            )
    return sorted(rows, key=lambda r: (r["db_alias"], r["project_name"]))


def _prepare_backend_content(
    rel_path: str, content: str, *, api_prefix: str = "/api"
) -> tuple[str, list[str], list[str]]:
    """After auto-fixes, return blocking violations (non-empty means write is rejected)."""
    from skill_package.core.fullstack_contract import (
        ensure_main_py_health_snippet,
        fix_relative_imports,
    )
    from skill_package.core.fullstack_enforce import blocking_errors_for_backend_file

    rel = rel_path.strip().lstrip("/")
    body = content
    autofix: list[str] = []
    if rel.endswith(".py"):
        body, ch = fix_relative_imports(body)
        autofix.extend(ch)
        if rel == "main.py":
            body, ch2 = ensure_main_py_health_snippet(body, api_prefix)
            autofix.extend(ch2)
    errors = blocking_errors_for_backend_file(rel, body)
    return body, autofix, errors


def _blocked_payload(violations: list[str], *, file_path: str) -> str:
    from skill_package.core.fullstack_enforce import spec_summary_text

    return json.dumps(
        {
            "ok": False,
            "blocked": True,
            "file_path": file_path,
            "violations": violations,
            "spec_summary": spec_summary_text(),
            "message": "Violates full-stack generation rules; write rejected. Fix violations and retry save_backend_file.",
        },
        ensure_ascii=False,
    )


def _after_backend_file_write(
    db_alias: str, project_name: str, file_path: str, target: Path, content: str | None = None
) -> dict:
    """After save/patch, sync manifest and record integration hints."""
    alias = validate_db_alias(db_alias)
    proj = _project_root(alias, project_name)
    extra: dict = {}
    rel = file_path.strip().lstrip("/")
    meta = _read_manifest_file(proj) or {}
    api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")

    if rel.endswith(".py"):
        from skill_package.core.fullstack_contract import (
            ensure_main_py_health_snippet,
            fix_relative_imports,
        )

        try:
            body = content if content is not None else target.read_text(encoding="utf-8")
        except OSError:
            body = ""
        # Normalized in save/patch; record only here
        if body and content is not None:
            extra["content_normalized"] = True

    if file_path.strip().endswith(API_MANIFEST_NAME) or (proj / API_MANIFEST_NAME).exists():
        meta = _read_manifest_file(proj)
        _sync_backend_manifest(alias, project_name, meta)
    if meta:
        port = meta.get("default_port", 8000)
        prefix = meta.get("api_prefix", "/api")
        extra["api_base_url"] = f"http://127.0.0.1:{port}{prefix}"
        if meta.get("linked_frontend"):
            extra["linked_frontend"] = meta["linked_frontend"]
        extra["frontend_next_step"] = (
            f"UI_build should call get_fullstack_api_contract(db_alias, frontend_project="
            f"{meta.get('linked_frontend')!r}) before writing preview.html"
            if meta.get("linked_frontend")
            else "Set linked_frontend in api_manifest.json, then let UI_build wire the frontend"
        )
    return extra


def _sync_backend_manifest(db_alias: str, project_name: str, meta: dict | None) -> None:
    proj_dir = _project_root(db_alias, project_name)
    manifest = read_manifest(db_alias)
    projects: list[dict] = list(manifest.get("backend_projects") or [])
    m = meta or {}
    entry = {
        "name": project_name,
        "path": f"backend/{project_name}",
        "has_database_connection": bool(m.get("has_database_connection")),
        "has_api_knowledge": (proj_dir / "api_knowledge.md").is_file(),
        "stack": m.get("stack"),
        "linked_frontend": m.get("linked_frontend"),
        "default_port": m.get("default_port"),
        "api_prefix": m.get("api_prefix"),
    }
    projects = [p for p in projects if p.get("name") != project_name]
    projects.append(entry)
    touch_manifest(db_alias, backend_projects=projects)


@register_skill_tool("backend", name="list_backend_projects", schema=list_schema)
def list_backend_projects(db_alias: str | None = None) -> str:
    projects = _scan_projects(db_alias)
    return json.dumps({"ok": True, "projects": projects, "count": len(projects)}, ensure_ascii=False)


@register_skill_tool("backend", name="check_db_connected_backend", schema=check_schema)
def check_db_connected_backend(db_alias: str) -> str:
    from skill_package.core.deliverables import audit_backend_project

    alias = validate_db_alias(db_alias)
    for row in _scan_projects(alias):
        if row.get("has_database_connection"):
            proj_dir = backend_dir(alias) / row["project_name"]
            meta = _read_manifest_file(proj_dir)
            deliverables = audit_backend_project(proj_dir)
            msg = "DB-connected backend exists; iterate on it."
            if deliverables["missing_required"]:
                msg += (
                    f" Warning: missing required files {deliverables['missing_required']}; "
                    "use save_backend_file before uvicorn can start."
                )
            if deliverables.get("linked_frontend") and not deliverables.get(
                "linked_frontend_exists"
            ):
                msg += (
                    f" Warning: linked_frontend={deliverables['linked_frontend']!r} frontend directory missing; "
                    "UI_build must create it—do not claim frontend is done."
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
            "workspace_backend": f"workspace/{alias}/backend/",
            "message": "No DB-connected backend found; create a project under backend/ and write api_manifest.json.",
        },
        ensure_ascii=False,
    )


@register_skill_tool("backend", name="read_backend_file", schema=read_schema)
def read_backend_file(db_alias: str, project_name: str, file_path: str) -> str:
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


@register_skill_tool("backend", name="save_backend_file", schema=save_schema)
def save_backend_file(db_alias: str, project_name: str, file_path: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rel = file_path.strip().lstrip("/")
        proj = _project_root(alias, project_name)
        meta = _read_manifest_file(proj) or {}
        api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        body, autofix, violations = _prepare_backend_content(rel, content, api_prefix=api_prefix)
        if violations:
            return _blocked_payload(violations, file_path=rel)
        target.write_text(body, encoding="utf-8")
        extra = _after_backend_file_write(alias, project_name, file_path, target, body)
        if autofix:
            extra["auto_fixed"] = autofix
        payload: dict = {
            "ok": True,
            "db_alias": alias,
            "project_name": project_name,
            "path": str(target),
            "workspace_path": f"workspace/{alias}/backend/{project_name}/{file_path.lstrip('/')}",
            "bytes": target.stat().st_size,
            "mode": "full_write",
            **extra,
        }
        proj = _project_root(alias, project_name)
        meta = _read_manifest_file(proj)
        if meta:
            port = meta.get("default_port", 8000)
            payload["run_hint"] = (
                f"Local run: cd workspace/{alias}/backend/{project_name} && "
                f"pip install -r requirements.txt && "
                f"uvicorn main:app --reload --port {port}"
            )
        return json.dumps(payload, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="patch_backend_file", schema=patch_schema)
def patch_backend_file(
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
        rel = file_path.strip().lstrip("/")
        patched_body = target.read_text(encoding="utf-8")
        meta = _read_manifest_file(_project_root(alias, project_name)) or {}
        api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        autofix: list[str] = []
        if rel in (API_MANIFEST_NAME, "requirements.txt") or rel.endswith(".py"):
            body, autofix, violations = _prepare_backend_content(
                rel,
                patched_body,
                api_prefix=api_prefix,
            )
            if violations:
                return _blocked_payload(violations, file_path=rel)
            if body != patched_body:
                target.write_text(body, encoding="utf-8")
            patched_body = body
        extra = _after_backend_file_write(
            alias, project_name, file_path, target, patched_body if rel.endswith(".py") else None
        )
        if autofix:
            extra["auto_fixed"] = autofix
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/backend/{project_name}/{file_path.lstrip('/')}",
                "mode": "patch",
                **patch_meta,
                **extra,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="get_backend_run_info", schema=run_info_schema)
def get_backend_run_info(db_alias: str, project_name: str) -> str:
    try:
        from skill_package.core.deliverables import audit_backend_project

        alias = validate_db_alias(db_alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir():
            return json.dumps(
                {"ok": False, "error": f"Project not found: backend/{project_name}/"},
                ensure_ascii=False,
            )
        meta = _read_manifest_file(proj) or {}
        port = int(meta.get("default_port") or 8000)
        prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        if prefix and (not prefix.startswith("/") or "（" in prefix or "）" in prefix):
            prefix = "/api"
        prefix = prefix.rstrip("/") or ""
        stack = meta.get("stack") or "fastapi"
        linked = meta.get("linked_frontend") or ""
        audit = audit_backend_project(proj)
        studio_cmd = f"uvicorn main:app --host 127.0.0.1 --port {port}"
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "stack": stack,
                "default_port": port,
                "api_prefix": prefix or "/api",
                "api_base_url": f"http://127.0.0.1:{port}{prefix}",
                "linked_frontend": linked,
                "workspace_path": f"workspace/{alias}/backend/{project_name}/",
                "ready_for_studio": audit.get("ready_for_studio", False),
                "studio_gaps": audit.get("studio_gaps") or [],
                "run_commands": [
                    f"cd skill_package/workspace/{alias}/backend/{project_name}",
                    "pip install -r requirements.txt",
                    f"uvicorn main:app --reload --host 127.0.0.1 --port {port}",
                ],
                "studio_run_command": studio_cmd,
                "studio_env_vars": [
                    "STUDIO_WORKSPACE_CONFIG",
                    "STUDIO_DB_ALIAS",
                    "STUDIO_STORAGE_MODE",
                    "STUDIO_LOCAL_SQLITE",
                    "DB_PASSWORD",
                    "DB_TARGET_PASSWORD",
                ],
                "studio_notes": (
                    "Skill Studio preview runs studio_run_command via backend_runner (no --reload), "
                    "injects studio_env_vars; main.py must import cleanly; api_manifest.api_prefix must be /api or empty string."
                ),
                "frontend_integration_hint": (
                    f"Point preview.html or Vite dev server at http://127.0.0.1:{port}{prefix}; "
                    f"document routes in api_knowledge.md and frontend ui_knowledge.md."
                ),
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


verify_fullstack_schema = {
    "type": "function",
    "function": {
        "name": "verify_fullstack_deliverables",
        "description": (
            "Read-only check that full-stack deliverables are complete (backend + frontend + key files). "
            "Required before telling the user the system is done; if system_complete is false, keep writing files per gaps."
        ),
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}

fullstack_contract_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_api_contract",
        "description": (
            "Return full-stack API contract (routes, api_base_url, preview_api_block). "
            "Call after backend main.py is ready and before UI_build writes preview.html; verify linked_frontend."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {"type": "string"},
                "backend_project": {"type": "string"},
            },
            "required": ["db_alias"],
        },
    },
}


scaffold_schema = {
    "type": "function",
    "function": {
        "name": "scaffold_fullstack_project",
        "description": (
            "[Preferred for new full-stack] Scaffold backend + frontend per hard rules "
            "(api_manifest, main.py, requirements, preview.html, knowledge docs). "
            "Then use save_backend_file for routers/business logic."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {"type": "string", "description": "Frontend directory name, e.g. my-app-web"},
                "backend_project": {"type": "string", "description": "Optional; default {frontend}-api"},
                "service_title": {"type": "string", "description": "Service/page title"},
                "write_to_disk": {
                    "type": "boolean",
                    "description": "When true, write files to disk; default true",
                },
            },
            "required": ["db_alias", "frontend_project"],
        },
    },
}

spec_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_generation_spec",
        "description": "Return full-stack generation hard rules (flow, forbidden patterns, completion gate). Read before new systems.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_skill_tool("backend", name="get_fullstack_generation_spec", schema=spec_schema)
def get_fullstack_generation_spec() -> str:
    from skill_package.core.fullstack_enforce import GENERATION_SPEC, spec_summary_text

    return json.dumps(
        {
            "ok": True,
            "summary": spec_summary_text(),
            "spec": GENERATION_SPEC,
        },
        ensure_ascii=False,
    )


@register_skill_tool("backend", name="scaffold_fullstack_project", schema=scaffold_schema)
def scaffold_fullstack_project(
    db_alias: str,
    frontend_project: str,
    backend_project: str | None = None,
    service_title: str = "Business System",
    write_to_disk: bool = True,
) -> str:
    from skill_package.core.fullstack_scaffold import build_scaffold_plan, write_scaffold_to_workspace
    from skill_package.workspace.paths import ensure_workspace

    try:
        alias = validate_db_alias(db_alias)
        ensure_workspace(alias)
        plan = build_scaffold_plan(
            alias,
            frontend_project=frontend_project,
            backend_project=backend_project,
            service_title=service_title or "Business System",
        )
        if write_to_disk:
            written = write_scaffold_to_workspace(plan)
            plan["written"] = written["written"]
            plan["message"] = (
                f"Scaffold written to backend/{plan['backend_project']} and "
                f"frontend/{plan['frontend_project']}; add routers and page logic next."
            )
        else:
            plan["message"] = "Scaffold plan generated (not written); call save_*_file for each artifact."
        return json.dumps(plan, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="get_fullstack_api_contract", schema=fullstack_contract_schema)
def get_fullstack_api_contract_backend(
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


@register_skill_tool("backend", name="verify_fullstack_deliverables", schema=verify_fullstack_schema)
def verify_fullstack_deliverables(db_alias: str) -> str:
    from skill_package.core.deliverables import verify_fullstack_status

    try:
        return json.dumps(verify_fullstack_status(db_alias), ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
