"""Browse knowledge documents under workspace/{db_alias}/dataset/."""

from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.workspace.paths import (
    dataset_dir,
    list_workspace_aliases,
    validate_db_alias,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_database_knowledge",
        "description": (
            "List Markdown knowledge docs under workspace/{db_alias}/dataset/. "
            "If db_alias is omitted, list docs across all workspaces."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {
                    "type": "string",
                    "description": "Customer workspace alias; omit to scan all workspaces",
                },
            },
            "required": [],
        },
    },
}

read_schema = {
    "type": "function",
    "function": {
        "name": "read_database_knowledge",
        "description": "Read a .md file under workspace/{db_alias}/dataset/",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "Customer workspace alias"},
                "file_name": {
                    "type": "string",
                    "description": "Path relative to dataset/, e.g. 20260521_order_domain.md",
                },
            },
            "required": ["db_alias", "file_name"],
        },
    },
}


def _resolve_md(db_alias: str, file_name: str) -> Path:
    alias = validate_db_alias(db_alias)
    name = file_name.strip().strip('"').strip("'")
    if not name.endswith(".md"):
        name += ".md"
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid file_name")
    if rel.parts and rel.parts[0] == "dataset":
        rel = Path(*rel.parts[1:])
    root = dataset_dir(alias).resolve()
    target = (root / rel).resolve()
    target.relative_to(root)
    if target.suffix.lower() != ".md":
        raise ValueError("Only .md files are allowed.")
    return target


@register_skill_tool(
    "database",
    name="list_database_knowledge",
    schema=list_schema,
    alias=["list_knowledge_docs"],
)
def list_database_knowledge(db_alias: str | None = None) -> str:
    aliases = [validate_db_alias(db_alias)] if db_alias and db_alias.strip() else list_workspace_aliases()
    files: list[dict[str, str]] = []
    for alias in aliases:
        root = dataset_dir(alias)
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            if p.name.startswith("_"):
                continue
            files.append(
                {
                    "db_alias": alias,
                    "file_name": p.relative_to(root).as_posix(),
                    "workspace_path": f"workspace/{alias}/dataset/{p.relative_to(root).as_posix()}",
                }
            )
    return json.dumps({"ok": True, "files": files, "count": len(files)}, ensure_ascii=False)


@register_skill_tool(
    "database",
    name="read_database_knowledge",
    schema=read_schema,
    alias=["read_knowledge_doc"],
)
def read_database_knowledge(db_alias: str, file_name: str) -> str:
    try:
        path = _resolve_md(db_alias, file_name)
        if not path.exists():
            return json.dumps({"ok": False, "error": f"File not found: {path}"}, ensure_ascii=False)
        content = path.read_text(encoding="utf-8")
        if len(content) > 50000:
            content = content[:50000] + "\n\n...[TRUNCATED]"
        rel = path.relative_to(dataset_dir(validate_db_alias(db_alias))).as_posix()
        return json.dumps(
            {"ok": True, "db_alias": validate_db_alias(db_alias), "file_name": rel, "content": content},
            ensure_ascii=False,
        )
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
