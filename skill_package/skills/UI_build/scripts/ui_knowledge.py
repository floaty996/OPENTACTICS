"""UI frontend knowledge: workspace/{db_alias}/frontend/{project_name}/ui_knowledge.md"""

from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.UI_build.paths import UI_KNOWLEDGE_NAME
from skill_package.skills.UI_build.scripts.ui_assets import (
    _project_root,
    _read_manifest_file,
    _sync_project_manifest,
)
from skill_package.workspace.paths import ensure_workspace, validate_db_alias

read_schema = {
    "type": "function",
    "function": {
        "name": "read_ui_knowledge",
        "description": (
            "Read workspace/{db_alias}/frontend/{project_name}/ui_knowledge.md "
            "(layout, styling, components, interaction)."
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
            "Save or update ui_knowledge.md (Markdown, YAML frontmatter recommended). "
            "After frontend work, document layout, styling, and component conventions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "content": {"type": "string", "description": "Full Markdown content"},
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
                    "error": f"ui_knowledge.md not found: frontend/{project_name}/",
                    "hint": "After generating the frontend, use save_ui_knowledge to create and maintain the UI doc.",
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
                    "error": f"Frontend project not found: frontend/{project_name}/. Use save_ui_file first.",
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
