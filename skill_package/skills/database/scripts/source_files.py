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
            "列举 workspace/{db_alias}/source_files/ 下已上传的 xlsx/csv 源数据文件。"
            "可与 MySQL 源库单独或组合使用。"
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
            "预览 workspace 源数据文件（xlsx/csv）：列名、行数、样例行。"
            "整理业务知识前可先调用；完整分析后写入 dataset/*.md。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "path": {
                    "type": "string",
                    "description": "config.source_files 中的相对路径，如 source_files/20260521_sales.csv",
                },
                "sheet": {
                    "type": "string",
                    "description": "xlsx 工作表名，省略则用第一个",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "样例行数，默认 20，最大 100",
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
    alias=["列举源文件", "源数据文件列表"],
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
    alias=["读取源文件", "预览源数据文件"],
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
