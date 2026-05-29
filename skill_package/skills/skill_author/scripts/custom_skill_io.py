from __future__ import annotations

import json

from skill_package.core.registry import register_skill_tool
from skill_package.custom_skills_store import (
    create_custom_skill,
    delete_custom_skill,
    dumps_json,
    list_custom_skill_ids,
    read_text_file,
    skill_dir,
    validate_skill_id,
    write_custom_skill_file,
)
from skill_package.skill_author_uploads import list_uploads, read_upload, validate_session_id

create_custom_skill_schema = {
    "type": "function",
    "function": {
        "name": "create_custom_skill",
        "description": "在 config/custom_skills/ 下新建用户自定义 Skill（含 SKILL.md）。",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "目录名，字母开头"},
                "name": {"type": "string", "description": "显示名"},
                "description": {"type": "string", "description": "简短描述"},
                "instructions": {"type": "string", "description": "SKILL.md 正文（frontmatter 之后）"},
                "skill_md": {
                    "type": "string",
                    "description": "完整 SKILL.md 内容（含 frontmatter）；提供时忽略 name/description/instructions",
                },
            },
            "required": ["skill_id"],
        },
    },
}

write_custom_skill_file_schema = {
    "type": "function",
    "function": {
        "name": "write_custom_skill_file",
        "description": "向已存在的自定义 Skill 写入或覆盖文件（如 references/xxx.md）。",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "file_path": {"type": "string", "description": "相对 skill 目录的路径"},
                "content": {"type": "string"},
            },
            "required": ["skill_id", "file_path", "content"],
        },
    },
}

list_custom_skills_schema = {
    "type": "function",
    "function": {
        "name": "list_custom_skills",
        "description": "列出所有用户自定义 Skill id。",
        "parameters": {"type": "object", "properties": {}},
    },
}

delete_custom_skill_schema = {
    "type": "function",
    "function": {
        "name": "delete_custom_skill",
        "description": "删除用户自定义 Skill（不可删除系统 skill）。",
        "parameters": {
            "type": "object",
            "properties": {"skill_id": {"type": "string"}},
            "required": ["skill_id"],
        },
    },
}

list_uploads_schema = {
    "type": "function",
    "function": {
        "name": "list_skill_author_uploads",
        "description": "列出当前 Skill 创建会话中用户上传的参考文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Skill 创建会话 id"},
            },
            "required": ["session_id"],
        },
    },
}

read_upload_schema = {
    "type": "function",
    "function": {
        "name": "read_skill_author_upload",
        "description": "读取当前会话中用户上传的参考文件内容（文本类）。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["session_id", "filename"],
        },
    },
}


@register_skill_tool(
    "skill_author",
    name="create_custom_skill",
    schema=create_custom_skill_schema,
    alias=["创建自定义skill", "新建skill"],
)
def tool_create_custom_skill(
    skill_id: str,
    name: str = "",
    description: str = "",
    instructions: str = "",
    skill_md: str = "",
) -> str:
    try:
        result = create_custom_skill(
            skill_id,
            name=name,
            description=description,
            instructions=instructions,
            skill_md=skill_md,
        )
        return dumps_json({"ok": True, **result})
    except Exception as e:
        return dumps_json({"ok": False, "error": str(e)})


@register_skill_tool(
    "skill_author",
    name="write_custom_skill_file",
    schema=write_custom_skill_file_schema,
    alias=["写入自定义skill文件"],
)
def tool_write_custom_skill_file(skill_id: str, file_path: str, content: str) -> str:
    try:
        validate_skill_id(skill_id)
        result = write_custom_skill_file(skill_id, file_path, content)
        return dumps_json({"ok": True, **result})
    except Exception as e:
        return dumps_json({"ok": False, "error": str(e)})


@register_skill_tool("skill_author", name="list_custom_skills", schema=list_custom_skills_schema)
def tool_list_custom_skills() -> str:
    return dumps_json({"ok": True, "skills": list_custom_skill_ids()})


@register_skill_tool("skill_author", name="delete_custom_skill", schema=delete_custom_skill_schema)
def tool_delete_custom_skill(skill_id: str) -> str:
    try:
        result = delete_custom_skill(skill_id)
        return dumps_json({"ok": True, **result})
    except Exception as e:
        return dumps_json({"ok": False, "error": str(e)})


@register_skill_tool(
    "skill_author",
    name="list_skill_author_uploads",
    schema=list_uploads_schema,
)
def tool_list_skill_author_uploads(session_id: str) -> str:
    try:
        sid = validate_session_id(session_id)
        return dumps_json({"ok": True, "session_id": sid, "files": list_uploads(sid)})
    except Exception as e:
        return dumps_json({"ok": False, "error": str(e)})


@register_skill_tool(
    "skill_author",
    name="read_skill_author_upload",
    schema=read_upload_schema,
)
def tool_read_skill_author_upload(session_id: str, filename: str) -> str:
    try:
        sid = validate_session_id(session_id)
        text = read_upload(sid, filename)
        return dumps_json({"ok": True, "session_id": sid, "filename": filename, "content": text})
    except Exception as e:
        return dumps_json({"ok": False, "error": str(e)})


def read_custom_skill_file(skill_id: str, file_path: str) -> str:
    root = skill_dir(validate_skill_id(skill_id))
    rel = str(file_path or "").strip().replace("\\", "/").lstrip("/")
    path = (root / rel).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(file_path)
    return read_text_file(path)
