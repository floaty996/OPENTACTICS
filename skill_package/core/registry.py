from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

SKILL_TOOL_REGISTRY: dict[str, "SkillTool"] = {}


@dataclass
class SkillTool:
    name: str
    skill_id: str
    func: Callable[..., Any]
    schema: dict[str, Any]
    alias: tuple[str, ...] = field(default_factory=tuple)


def register_skill_tool(skill_id: str, name: str, schema: dict[str, Any], alias: list[str] | None = None):
    """將函式註冊為某個 skill 專屬工具（skill_id 為 skills/ 下目錄名）。"""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        SKILL_TOOL_REGISTRY[name] = SkillTool(
            name=name,
            skill_id=skill_id,
            func=func,
            schema=schema,
            alias=tuple(alias or ()),
        )
        return func

    return decorator


def get_tool_function(name: str) -> Callable[..., Any] | None:
    for tool in SKILL_TOOL_REGISTRY.values():
        if name == tool.name or name in tool.alias:
            return tool.func
    return None


def get_tool_schemas_for_skill(skill_id: str) -> list[dict[str, Any]]:
    """回傳該 skill 註冊之工具的 OpenAI function schema 列表。"""
    return [t.schema for t in SKILL_TOOL_REGISTRY.values() if t.skill_id == skill_id]


def get_tool_schemas_for_skills(skill_ids: Iterable[str]) -> list[dict[str, Any]]:
    """多個 skill 合併取得工具 schema（智能體啟用多個 skill 時用）。"""
    allow = frozenset(skill_ids)
    return [t.schema for t in SKILL_TOOL_REGISTRY.values() if t.skill_id in allow]


_TOOL_LABEL_CACHE: dict[str, str] | None = None


def _short_tool_description(desc: str, *, max_len: int = 52) -> str:
    text = " ".join(str(desc or "").split())
    if not text:
        return ""
    for sep in ("。", "；", ";", ".", "，", ",", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def get_tool_display_labels() -> dict[str, str]:
    """工具名 / 别名 -> 中文简短说明（供 Studio 展示）。"""
    global _TOOL_LABEL_CACHE
    if _TOOL_LABEL_CACHE is not None:
        return dict(_TOOL_LABEL_CACHE)

    labels: dict[str, str] = {}
    for tool in SKILL_TOOL_REGISTRY.values():
        fn = tool.schema.get("function") if isinstance(tool.schema, dict) else None
        fn = fn if isinstance(fn, dict) else {}
        raw_desc = fn.get("description") or tool.name
        label = _short_tool_description(str(raw_desc)) or tool.name
        labels[tool.name] = label
        for alias in tool.alias:
            labels[str(alias)] = label

    _TOOL_LABEL_CACHE = labels
    return dict(labels)


def get_tool_display_label(name: str) -> str:
    """返回工具的中文展示名；未知工具则返回原名。"""
    key = str(name or "").strip()
    if not key:
        return "工具调用"
    return get_tool_display_labels().get(key, key)
