"""查阅 workspace/{db_alias}/dataset/ 下知识文档。"""

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
            "列举 workspace/{db_alias}/dataset/ 下的 Markdown 知识文档。"
            "db_alias 为空则列举所有工作区下的 dataset 文档。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {
                    "type": "string",
                    "description": "客户库别名；省略则扫描全部工作区",
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
        "description": "读取 workspace/{db_alias}/dataset/ 下指定 .md 文件",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "客户库别名"},
                "file_name": {
                    "type": "string",
                    "description": "相对 dataset/ 的路径，如 20260521_order_domain.md",
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
        raise ValueError("file_name 非法")
    if rel.parts and rel.parts[0] == "dataset":
        rel = Path(*rel.parts[1:])
    root = dataset_dir(alias).resolve()
    target = (root / rel).resolve()
    target.relative_to(root)
    if target.suffix.lower() != ".md":
        raise ValueError("仅允许读取 .md 文件。")
    return target


@register_skill_tool(
    "database",
    name="list_database_knowledge",
    schema=list_schema,
    alias=["列举知识文档", "查看已有文档"],
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
    alias=["读取知识文档"],
)
def read_database_knowledge(db_alias: str, file_name: str) -> str:
    try:
        path = _resolve_md(db_alias, file_name)
        if not path.exists():
            return json.dumps({"ok": False, "error": f"文件不存在: {path}"}, ensure_ascii=False)
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
