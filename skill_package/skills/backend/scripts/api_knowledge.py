"""后端 API 知识文档：workspace/{db_alias}/backend/{project_name}/api_knowledge.md"""

from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.backend.paths import API_KNOWLEDGE_NAME
from skill_package.skills.backend.scripts.backend_assets import (
    _project_root,
    _read_manifest_file,
    _sync_backend_manifest,
)
from skill_package.workspace.paths import ensure_workspace, validate_db_alias

read_schema = {
    "type": "function",
    "function": {
        "name": "read_api_knowledge",
        "description": (
            "读取 workspace/{db_alias}/backend/{project_name}/api_knowledge.md，"
            "含 REST 路由、请求/响应约定、与数据库表映射等。"
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
        "name": "save_api_knowledge",
        "description": (
            "保存或更新 api_knowledge.md（Markdown，建议含 YAML frontmatter）。"
            "在生成/迭代后端后，整理路由、鉴权、与 frontend 的对接说明。"
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
    return _project_root(db_alias, project_name) / API_KNOWLEDGE_NAME


@register_skill_tool("backend", name="read_api_knowledge", schema=read_schema)
def read_api_knowledge(db_alias: str, project_name: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        path = _knowledge_path(alias, project_name)
        if not path.is_file():
            return json.dumps(
                {
                    "ok": False,
                    "error": f"api_knowledge.md 不存在: backend/{project_name}/",
                    "hint": "生成后端后请用 save_api_knowledge 创建并维护 API 知识文档。",
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
                "workspace_path": f"workspace/{alias}/backend/{project_name}/{API_KNOWLEDGE_NAME}",
                "content": content,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="save_api_knowledge", schema=save_schema)
def save_api_knowledge(db_alias: str, project_name: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        ensure_workspace(alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir() and not (proj / "api_manifest.json").is_file():
            return json.dumps(
                {
                    "ok": False,
                    "error": f"后端工程不存在: backend/{project_name}/，请先 save_backend_file 创建工程。",
                },
                ensure_ascii=False,
            )
        path = _knowledge_path(alias, project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        meta = _read_manifest_file(proj)
        _sync_backend_manifest(alias, project_name, meta)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "workspace_path": f"workspace/{alias}/backend/{project_name}/{API_KNOWLEDGE_NAME}",
                "bytes": path.stat().st_size,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
