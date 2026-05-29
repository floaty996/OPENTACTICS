"""工作区对话持久化：skill_package/workspace/{db_alias}/conversations/*.json"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_package.workspace.paths import ensure_workspace, validate_db_alias, workspace_dir

_CONV_ID_RE = re.compile(r"^c_[A-Za-z0-9_-]{8,64}$")
_MAX_MESSAGES = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_conversation_id(conversation_id: str) -> str:
    cid = conversation_id.strip()
    if not cid or not _CONV_ID_RE.match(cid):
        raise ValueError("conversation_id 格式无效")
    return cid


def conversations_dir(db_alias: str) -> Path:
    alias = validate_db_alias(db_alias)
    return workspace_dir(alias) / "conversations"


def conversation_path(db_alias: str, conversation_id: str) -> Path:
    cid = validate_conversation_id(conversation_id)
    return conversations_dir(db_alias) / f"{cid}.json"


def title_from_message(text: str, *, max_len: int = 48) -> str:
    t = " ".join(str(text).strip().split())
    if not t:
        return "新对话"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    if len(cleaned) > _MAX_MESSAGES:
        cleaned = cleaned[-_MAX_MESSAGES:]
    return cleaned


def list_conversations(db_alias: str) -> list[dict[str, Any]]:
    """列举对话摘要，按更新时间倒序。"""
    alias = validate_db_alias(db_alias)
    root = conversations_dir(alias)
    root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            messages = data.get("messages") or []
            if not isinstance(messages, list):
                messages = []
            items.append(
                {
                    "id": data.get("id") or path.stem,
                    "title": data.get("title") or "未命名对话",
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(messages),
                }
            )
        except (json.JSONDecodeError, OSError, ValueError):
            continue
    items.sort(key=lambda x: (x.get("updated_at") or "", x.get("id") or ""), reverse=True)
    return items


def load_conversation(db_alias: str, conversation_id: str) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    path = conversation_path(alias, conversation_id)
    if not path.is_file():
        raise FileNotFoundError(f"对话不存在: {conversation_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("对话文件格式无效")
    data["id"] = validate_conversation_id(str(data.get("id") or conversation_id))
    data["messages"] = _normalize_messages(data.get("messages") or [])
    return data


def save_conversation(db_alias: str, data: dict[str, Any]) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    cid = validate_conversation_id(str(data.get("id", "")))
    messages = _normalize_messages(data.get("messages") or [])
    title = str(data.get("title") or "").strip() or "新对话"
    if title == "新对话" and messages:
        first_user = next((m for m in messages if m["role"] == "user"), None)
        if first_user:
            title = title_from_message(first_user["content"])

    payload = {
        "id": cid,
        "title": title,
        "created_at": data.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "messages": messages,
    }
    ensure_workspace(alias)
    path = conversation_path(alias, cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def create_conversation(db_alias: str, *, title: str = "新对话") -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    cid = f"c_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"
    return save_conversation(
        alias,
        {
            "id": cid,
            "title": title,
            "created_at": _now_iso(),
            "messages": [],
        },
    )


def delete_conversation(db_alias: str, conversation_id: str) -> None:
    """删除对话文件。"""
    alias = validate_db_alias(db_alias)
    path = conversation_path(alias, conversation_id)
    if not path.is_file():
        raise FileNotFoundError(f"对话不存在: {conversation_id}")
    path.unlink()


def save_conversation_messages(
    db_alias: str,
    conversation_id: str,
    messages: list[dict[str, str]],
    *,
    title: str | None = None,
) -> dict[str, Any]:
    try:
        existing = load_conversation(db_alias, conversation_id)
    except FileNotFoundError:
        existing = {"id": conversation_id, "title": title or "新对话", "created_at": _now_iso()}
    if title:
        existing["title"] = title
    existing["messages"] = _normalize_messages(messages)
    return save_conversation(db_alias, existing)
