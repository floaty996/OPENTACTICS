from __future__ import annotations

import json
from datetime import datetime, timezone

from skill_package.core.registry import register_skill_tool
from skill_package.workspace.local_store import (
    DEFAULT_LOCAL_SQLITE_REL,
    ensure_local_sqlite,
    resolve_storage_mode,
)
from skill_package.workspace.config_loader import (
    is_redacted_secret,
    mask_config_secrets,
    merge_preserved_secrets,
    parse_database_list,
)
from skill_package.workspace.source_files_store import normalize_source_files
from skill_package.workspace.paths import (
    config_path,
    ensure_workspace,
    list_workspace_aliases,
    touch_manifest,
    validate_db_alias,
)

_SUPPORTED_DB = frozenset({"mysql", "postgresql", "sqlite"})

save_schema = {
    "type": "function",
    "function": {
        "name": "save_database_config",
        "description": (
            "Save to workspace/{db_alias}/config.json. "
            "source_databases optional; when target_database is empty, backend data uses local SQLite (data/app.db)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "db_type": {"type": "string", "enum": ["mysql", "postgresql", "sqlite"]},
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "user": {"type": "string", "description": "Source DB read-only account (recommended)"},
                "password": {"type": "string"},
                "source_databases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Source database names (agent read-only documentation)",
                },
                "target_database": {
                    "type": "string",
                    "description": "Target database name (only DB where agent may DDL/DML)",
                },
                "target_user": {"type": "string", "description": "Target DB user; defaults to user"},
                "target_password": {"type": "string", "description": "Target DB password; defaults to password"},
                "file_path": {"type": "string"},
            },
            "required": ["db_alias", "db_type"],
        },
    },
}

list_schema = {
    "type": "function",
    "function": {
        "name": "list_database_configs",
        "description": "List workspace config.json files (passwords redacted)",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

read_schema = {
    "type": "function",
    "function": {
        "name": "read_database_config",
        "description": (
            "Read config.json (password fields returned as *** to the model; disk keeps real secrets; "
            "never pass *** to save_database_config)"
        ),
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}

read_manifest_schema = {
    "type": "function",
    "function": {
        "name": "read_workspace_manifest",
        "description": "Read manifest.json",
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}


@register_skill_tool("UI_build", name="save_database_config", schema=save_schema)
def save_database_config(
    db_alias: str,
    db_type: str,
    source_databases: list[str] | None = None,
    target_database: str | None = None,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    target_user: str | None = None,
    target_password: str | None = None,
    file_path: str | None = None,
) -> str:
    try:
        alias = validate_db_alias(db_alias)
        kind = db_type.strip().lower()
        if kind not in _SUPPORTED_DB:
            raise ValueError(f"Unsupported db_type: {db_type}")

        sources = parse_database_list(source_databases or [])
        target = ""
        if target_database and str(target_database).strip():
            target = parse_database_list([target_database])[0]
        if target and target in sources:
            raise ValueError("target_database must not duplicate an entry in source_databases")

        storage_mode = "mysql" if target else "local"
        local_rel = DEFAULT_LOCAL_SQLITE_REL

        if storage_mode == "local":
            ensure_local_sqlite(alias, rel_path=local_rel)
            if sources and not all([host, user]):
                raise ValueError("When source databases are configured, host and user are required")
            if sources and is_redacted_secret(password):
                raise ValueError("When source databases are configured, a valid password is required")
        elif kind == "sqlite":
            if not file_path or not str(file_path).strip():
                raise ValueError("sqlite requires file_path")
        elif not all([host, user]):
            raise ValueError(f"{kind} requires host and user")

        ensure_workspace(alias)
        path = config_path(alias)
        existing: dict | None = None
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                existing = raw if isinstance(raw, dict) else None
            except (json.JSONDecodeError, OSError):
                existing = None

        payload = {
            "db_alias": alias,
            "db_type": kind if storage_mode == "mysql" else "sqlite",
            "storage_mode": storage_mode,
            "local_sqlite_path": local_rel,
            "host": host or "",
            "port": port or 3306,
            "user": user or "",
            "password": password or "",
            "source_databases": sources,
            "target_database": target,
            "target_user": target_user or user or "",
            "target_password": target_password if target_password is not None else password or "",
            "file_path": file_path or (local_rel if storage_mode == "local" else file_path),
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        payload = merge_preserved_secrets(payload, existing)
        if existing:
            payload["source_files"] = normalize_source_files(existing.get("source_files"))
        if storage_mode == "mysql" and sources and is_redacted_secret(payload.get("password")):
            raise ValueError(
                "No valid database password provided. *** from read_database_config is redacted only; "
                "ask the user to set password in Studio init or pass a real password to save_database_config."
            )
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        touch_manifest(
            alias,
            has_config=True,
            storage_mode=storage_mode,
            source_databases=sources,
            target_database=target,
        )
        msg = (
            "No target DB configured: backend data will use workspace local SQLite (data/app.db)."
            if storage_mode == "local"
            else "Source DBs are read-only; DDL/DML allowed on target_database only."
        )
        return json.dumps(
            {
                "ok": True,
                "path": str(path),
                "db_alias": alias,
                "config": mask_config_secrets(payload),
                "message": msg,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="list_database_configs", schema=list_schema)
def list_database_configs() -> str:
    configs = []
    for alias in list_workspace_aliases():
        p = config_path(alias)
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                configs.append({"db_alias": alias, "config": mask_config_secrets(data), "path": str(p)})
        except (json.JSONDecodeError, OSError):
            configs.append({"db_alias": alias, "error": "Failed to parse"})
    return json.dumps({"ok": True, "configs": configs}, ensure_ascii=False)


@register_skill_tool("UI_build", name="read_database_config", schema=read_schema)
def read_database_config(db_alias: str) -> str:
    try:
        from skill_package.workspace.config_loader import load_workspace_config

        alias = validate_db_alias(db_alias)
        data = load_workspace_config(alias)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "config": mask_config_secrets(data),
                "path": str(config_path(alias)),
                "note": "password/target_password are redacted as *** in tool output; config.json on disk keeps real values.",
            },
            ensure_ascii=False,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="read_workspace_manifest", schema=read_manifest_schema)
def read_workspace_manifest(db_alias: str) -> str:
    try:
        from skill_package.workspace.paths import manifest_path, read_manifest

        alias = validate_db_alias(db_alias)
        mp = manifest_path(alias)
        if not mp.exists():
            ensure_workspace(alias)
        return json.dumps(
            {"ok": True, "db_alias": alias, "manifest": read_manifest(alias), "path": str(mp)},
            ensure_ascii=False,
        )
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
