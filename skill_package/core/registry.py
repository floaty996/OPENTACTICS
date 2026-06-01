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
    """Register a function as a skill-specific tool (skill_id is the directory under skills/)."""

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
    """OpenAI function schemas registered for one skill."""
    return [t.schema for t in SKILL_TOOL_REGISTRY.values() if t.skill_id == skill_id]


def get_tool_schemas_for_skills(skill_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Merged tool schemas when multiple skills are enabled for one agent."""
    allow = frozenset(skill_ids)
    return [t.schema for t in SKILL_TOOL_REGISTRY.values() if t.skill_id in allow]


_TOOL_LABEL_CACHE: dict[str, str] | None = None


def _short_tool_description(desc: str, *, max_len: int = 52) -> str:
    text = " ".join(str(desc or "").split())
    if not text:
        return ""
    for sep in (".", ";", ",", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def get_tool_display_labels() -> dict[str, str]:
    """Map tool name / alias -> short label for Studio UI."""
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
    """Short display label for a tool; unknown names pass through."""
    key = str(name or "").strip()
    if not key:
        return "Tool call"
    return get_tool_display_labels().get(key, key)
