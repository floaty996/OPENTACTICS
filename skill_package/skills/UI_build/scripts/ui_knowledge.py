"""UI 前端知识文档：workspace/{db_alias}/frontend/{project_name}/ui_knowledge.md"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.UI_build.scripts.ui_assets import (
    _project_root,
    _read_manifest_file,
    _sync_project_manifest,
)
from skill_package.workspace.paths import ensure_workspace, validate_db_alias

UI_KNOWLEDGE_NAME = "ui_knowledge.md"

read_schema = {
    "type": "function",
    "function": {
        "name": "read_ui_knowledge",
        "description": (
            "读取 workspace/{db_alias}/frontend/{project_name}/ui_knowledge.md，"
            "含样式、排版、组件与交互等前端知识。"
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

save_schema = {
    "type": "function",
    "function": {
        "name": "save_ui_knowledge",
        "description": (
            "保存或更新 ui_knowledge.md（Markdown，建议含 YAML frontmatter）。"
            "在生成/迭代前端后，根据对话与实现整理样式、排版、组件约定等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "content": {"type": "string", "description": "完整 Markdown 内容"},
            },
            "required": ["db_alias", "project_name", "content"],
        },
    },
}


def _knowledge_path(db_alias: str, project_name: str) -> Path:
    return _project_root(db_alias, project_name) / UI_KNOWLEDGE_NAME


@register_skill_tool("UI_build", name="read_ui_knowledge", schema=read_schema)
def read_ui_knowledge(db_alias: str, project_name: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        path = _knowledge_path(alias, project_name)
        if not path.is_file():
            return json.dumps(
                {
                    "ok": False,
                    "error": f"ui_knowledge.md 不存在: frontend/{project_name}/",
                    "hint": "生成前端后请用 save_ui_knowledge 创建并维护 UI 知识文档。",
                },
                ensure_ascii=False,
            )
        content = path.read_text(encoding="utf-8")
        if len(content) > 80000:
            content = content[:80000] + "\n...[TRUNCATED]"
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{UI_KNOWLEDGE_NAME}",
                "content": content,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="save_ui_knowledge", schema=save_schema)
def save_ui_knowledge(db_alias: str, project_name: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        ensure_workspace(alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir() and not (proj / "ui_manifest.json").is_file():
            return json.dumps(
                {
                    "ok": False,
                    "error": f"前端工程不存在: frontend/{project_name}/，请先 save_ui_file 创建工程。",
                },
                ensure_ascii=False,
            )
        path = _knowledge_path(alias, project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        meta = _read_manifest_file(proj)
        _sync_project_manifest(alias, project_name, meta)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{UI_KNOWLEDGE_NAME}",
                "bytes": path.stat().st_size,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
