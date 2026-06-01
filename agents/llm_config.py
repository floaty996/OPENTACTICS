"""Resolve LLM provider and credentials for Studio chat (per-saas workspace + global DeepSeek)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.deepseek_backend import DEFAULT_CONFIG_PATH, load_deepseek_config
from skill_package.workspace.config_loader import is_redacted_secret, load_workspace_config

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GEMINI_CONFIG_PATH = _ROOT / "config" / "gemini.json"

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def load_gemini_global_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path or DEFAULT_GEMINI_CONFIG_PATH).resolve()
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"Gemini config not found: {cfg_path}\n"
            f"Copy {_ROOT / 'config/gemini.example.json'} to {DEFAULT_GEMINI_CONFIG_PATH}"
        )
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a JSON object: {cfg_path}")
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        raise ValueError(f"Set api_key in {cfg_path}")
    return {
        "api_key": api_key,
        "base_url": str(data.get("base_url") or GEMINI_OPENAI_BASE_URL).strip(),
        "model": str(data.get("model") or DEFAULT_GEMINI_MODEL).strip(),
        "max_tool_rounds": int(data.get("max_tool_rounds", 50)),
        "max_tokens": int(data.get("max_tokens", 8192)),
        "timeout_seconds": float(data.get("timeout_seconds", 300)),
    }


def normalize_llm_provider(value: Any) -> str:
    p = str(value or "deepseek").strip().lower()
    return p if p in ("deepseek", "gemini") else "deepseek"


def load_agent_config(db_alias: str | None = None) -> dict[str, Any]:
    """Build OpenAI-compatible client settings for the active saas LLM provider."""
    provider = "deepseek"
    gemini_key = ""
    gemini_model = DEFAULT_GEMINI_MODEL
    ws: dict[str, Any] = {}

    if db_alias:
        try:
            ws = load_workspace_config(db_alias)
            provider = normalize_llm_provider(ws.get("llm_provider"))
            gemini_key = str(ws.get("gemini_api_key") or "").strip()
            gemini_model = str(ws.get("gemini_model") or DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
        except FileNotFoundError:
            ws = {}

    if provider == "gemini":
        base_url = GEMINI_OPENAI_BASE_URL
        max_tool_rounds = 50
        max_tokens = 8192
        timeout_seconds = 300.0
        try:
            g_global = load_gemini_global_config()
            base_url = str(g_global.get("base_url") or base_url)
            max_tool_rounds = int(g_global.get("max_tool_rounds", max_tool_rounds))
            max_tokens = int(g_global.get("max_tokens", max_tokens))
            timeout_seconds = float(g_global.get("timeout_seconds", timeout_seconds))
            if not gemini_key or is_redacted_secret(gemini_key):
                gemini_key = g_global["api_key"]
            if not str(ws.get("gemini_model") or "").strip():
                gemini_model = str(g_global.get("model") or gemini_model)
        except FileNotFoundError:
            pass
        if not gemini_key or is_redacted_secret(gemini_key):
            raise ValueError(
                "Gemini API key missing. Set it in saas setup or config/gemini.json."
            )
        return {
            "provider": "gemini",
            "api_key": gemini_key,
            "base_url": base_url,
            "model": gemini_model,
            "max_tool_rounds": max_tool_rounds,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
        }

    ds = load_deepseek_config()
    return {"provider": "deepseek", **ds}


def workspace_llm_status(db_alias: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """LLM readiness for status UI (no secret values)."""
    data = raw
    if data is None:
        try:
            data = load_workspace_config(db_alias)
        except Exception:
            data = {}
    provider = normalize_llm_provider(data.get("llm_provider"))
    gemini_key = str(data.get("gemini_api_key") or "").strip()
    has_gemini = bool(gemini_key) and not is_redacted_secret(gemini_key)
    has_deepseek = False
    deepseek_error = ""
    try:
        load_deepseek_config()
        has_deepseek = True
    except Exception as e:
        deepseek_error = str(e)
    if provider == "gemini":
        ready = has_gemini
        if not ready:
            try:
                load_gemini_global_config()
                ready = True
                has_gemini = True
            except Exception:
                pass
    else:
        ready = has_deepseek
    return {
        "llm_provider": provider,
        "has_gemini": has_gemini,
        "has_deepseek": has_deepseek,
        "deepseek_error": deepseek_error,
        "gemini_model": str(data.get("gemini_model") or DEFAULT_GEMINI_MODEL),
        "llm_ready": ready,
    }
