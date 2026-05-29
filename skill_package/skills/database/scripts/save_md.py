from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.workspace.file_patch import patch_text_file
from skill_package.workspace.paths import dataset_dir, ensure_workspace, read_manifest, touch_manifest, validate_db_alias

save_md_schema = {
    "type": "function",
    "function": {
        "name": "save_markdown",
        "description": (
            "整文件写入 dataset/ 下 .md 知识文档；新建或大改用。"
            "小范围修改请优先 patch_markdown。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "客户库别名"},
                "file_path": {
                    "type": "string",
                    "description": "相对 dataset/ 的路径，如 20260521_order_domain.md",
                },
                "content": {"type": "string", "description": "Markdown 正文"},
            },
            "required": ["db_alias", "file_path", "content"],
        },
    },
}

patch_md_schema = {
    "type": "function",
    "function": {
        "name": "patch_markdown",
        "description": (
            "按片段替换 dataset/ 下已有 .md 文件（old_string → new_string）。"
            "修改前须先读取该文档并复制精确原文。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
                "occurrence": {"type": "integer"},
            },
            "required": ["db_alias", "file_path", "old_string", "new_string"],
        },
    },
}


def _resolve_target(db_alias: str, file_path: str) -> Path:
    alias = validate_db_alias(db_alias)
    raw = file_path.strip().strip('"').strip("'")
    if not raw:
        raise ValueError("file_path 不能为空。")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("file_path 非法")
    if rel.parts and rel.parts[0] == "dataset":
        rel = Path(*rel.parts[1:])
    root = dataset_dir(alias).resolve()
    target = (root / rel).resolve()
    target.relative_to(root)
    if target.suffix.lower() != ".md":
        raise ValueError(f"仅允许保存 .md 文件，当前扩展名: {target.suffix!r}")
    return target


@register_skill_tool(
    "database",
    name="save_markdown",
    schema=save_md_schema,
    alias=["保存md", "写入数据整理知识文档", "保存markdown"],
)
def save_markdown(db_alias: str, file_path: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        ensure_workspace(alias)
        target = _resolve_target(alias, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel = target.relative_to(dataset_dir(alias)).as_posix()
        manifest = read_manifest(alias)
        files: list[str] = list(manifest.get("knowledge_files") or [])
        entry = f"dataset/{rel}"
        if entry not in files:
            files.append(entry)
        touch_manifest(alias, knowledge_files=files)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/dataset/{rel}",
                "bytes": target.stat().st_size,
                "mode": "full_write",
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool(
    "database",
    name="patch_markdown",
    schema=patch_md_schema,
    alias=["片段替换markdown", "patch_dataset_md"],
)
def patch_markdown(
    db_alias: str,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    occurrence: int = 1,
) -> str:
    try:
        alias = validate_db_alias(db_alias)
        target = _resolve_target(alias, file_path)
        patch_meta = patch_text_file(
            target,
            old_string,
            new_string,
            replace_all=bool(replace_all),
            occurrence=int(occurrence or 1),
        )
        rel = target.relative_to(dataset_dir(alias)).as_posix()
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/dataset/{rel}",
                "mode": "patch",
                **patch_meta,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
