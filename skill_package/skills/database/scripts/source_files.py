from __future__ import annotations

import json

from skill_package.core.registry import register_skill_tool
from skill_package.workspace.source_files_store import (
    list_source_files as _list_source_files,
    read_source_file_preview,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_source_files",
        "description": (
            "List xlsx/csv source files under workspace/{db_alias}/source_files/. "
            "Can be used alone or together with MySQL source databases."
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
        "name": "read_source_file",
        "description": (
            "Preview a workspace source file (xlsx/csv): columns, row count, sample rows. "
            "Call before documenting business knowledge; write full analysis to dataset/*.md."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "path": {
                    "type": "string",
                    "description": "Relative path from config.source_files, e.g. source_files/20260521_sales.csv",
                },
                "sheet": {
                    "type": "string",
                    "description": "xlsx sheet name; default first sheet",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Sample row count, default 20, max 100",
                },
            },
            "required": ["db_alias", "path"],
        },
    },
}


@register_skill_tool(
    "database",
    name="list_source_files",
    schema=list_schema,
    alias=["list_source_data_files"],
)
def list_source_files(db_alias: str) -> str:
    try:
        files = _list_source_files(db_alias, verify_disk=True)
        return json.dumps({"ok": True, "db_alias": db_alias, "source_files": files}, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool(
    "database",
    name="read_source_file",
    schema=read_schema,
    alias=["preview_source_file"],
)
def read_source_file(
    db_alias: str,
    path: str,
    sheet: str | None = None,
    max_rows: int = 20,
) -> str:
    try:
        preview = read_source_file_preview(db_alias, path, sheet=sheet, max_rows=max_rows)
        return json.dumps(preview, ensure_ascii=False, default=str)
    except (ValueError, FileNotFoundError, RuntimeError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
