"""
DeepSeek 智能体（OpenAI 兼容 API + skill 工具调用）。

配置：config/deepseek.json（可参考 deepseek.example.json）
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from openai import OpenAI

from skill_package.core.registry import get_tool_display_label

ToolRunner = Callable[[str, dict[str, Any]], str]

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = _ROOT / "config" / "deepseek.json"


def load_deepseek_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path or DEFAULT_CONFIG_PATH).resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {cfg_path}\n"
            f"请复制 {_ROOT / 'config/deepseek.example.json'} 为 {DEFAULT_CONFIG_PATH}"
        )

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"配置须为 JSON 对象: {cfg_path}")

    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        raise ValueError(f"请在 {cfg_path} 中填写 api_key")

    return {
        "api_key": api_key,
        "base_url": data.get("base_url") or "https://api.deepseek.com",
        "model": data.get("model") or "deepseek-chat",
        "max_tool_rounds": int(data.get("max_tool_rounds", 50)),
        "max_tokens": int(data.get("max_tokens", 8192)),
        "timeout_seconds": float(data.get("timeout_seconds", 300)),
    }


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return args if isinstance(args, dict) else {}


class DeepSeekAgent:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        model: str,
        tool_runner: ToolRunner,
        max_tool_rounds: int = 50,
        max_tokens: int = 8192,
        timeout_seconds: float = 300.0,
    ) -> None:
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )
        self.model = model
        self.tool_runner = tool_runner
        self.max_tool_rounds = max_tool_rounds
        self.max_tokens = max_tokens

    def chat(
        self,
        system_prompt: str,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for item in history or []:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        if (question or "").strip():
            messages.append({"role": "user", "content": question.strip()})
        if len(messages) < 2:
            yield "[错误] 无有效用户消息\n"
            return

        tool_defs = tools or None
        for round_idx in range(self.max_tool_rounds):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tool_defs,
                max_tokens=self.max_tokens,
            )
            choice = resp.choices[0]
            msg = choice.message
            finish = getattr(choice, "finish_reason", None) or ""

            text = (msg.content or "").strip()

            if not msg.tool_calls:
                if msg.content:
                    yield msg.content
                # 已有完整正文则结束；否则流式补全（禁止再调工具，避免输出半截就停）
                if not text:
                    yield from self._stream_answer(messages)
                elif finish == "length":
                    yield "\n\n[回复因长度上限被截断，可输入「请继续」补全。]\n"
                return

            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                name = tc.function.name
                label = get_tool_display_label(name)
                yield f"\n[调用工具 {label}]\n"
                try:
                    tool_out = self.tool_runner(
                        name, _parse_tool_args(tc.function.arguments)
                    )
                except Exception as exc:
                    tool_out = json.dumps(
                        {"ok": False, "error": str(exc)},
                        ensure_ascii=False,
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_out,
                    }
                )

        yield "\n[已达最大工具调用轮数]\n"
        yield from self._stream_final_summary(messages, hit_max_rounds=True)

    def _stream_final_summary(
        self,
        messages: list[dict[str, Any]],
        *,
        hit_max_rounds: bool = False,
    ) -> Iterator[str]:
        """工具阶段结束后，强制用自然语言向用户说明已完成的工作（不再调用工具）。"""
        hint = (
            "请根据上文工具执行结果，用**简洁中文**向用户写最终回复（仅结论与摘要，禁止推理独白）。"
            "说明：已完成哪些操作、关键结论、产物在 workspace 下的路径、"
            "如何在 Skill Studio 预览。"
            "不要调用工具；不要写 Wait/Let me/让我检查/两种可能 等推演；不要只输出工具名。"
        )
        if hit_max_rounds:
            hint = (
                "（工具调用轮数已达上限，请直接汇总回复。）"
                + hint
            )
        messages.append({"role": "user", "content": hint})
        yield from self._stream_answer(messages)

    def _stream_answer(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        """流式输出最终回答；显式关闭 tools，避免模型在输出中途再次发起工具调用导致截断。"""
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                tools=None,
                max_tokens=self.max_tokens,
            )
            finish_reason = None
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta and delta.content:
                    yield delta.content
            if finish_reason == "length":
                yield "\n\n[回复因长度上限被截断，可输入「请继续」补全。]\n"
        except Exception as exc:
            yield f"\n\n[输出中断: {exc}]\n"
            raise


def get_agent_backend(
    tool_runner: ToolRunner | None = None,
    config_path: str | Path | None = None,
    *,
    db_alias: str | None = None,
) -> DeepSeekAgent:
    if db_alias:
        from agents.llm_config import load_agent_config

        cfg = load_agent_config(db_alias)
    else:
        cfg = load_deepseek_config(config_path)

    if tool_runner is None:
        from skill_package import get_tool_function

        def tool_runner(name: str, args: dict[str, Any]) -> str:
            fn = get_tool_function(name)
            if fn is None:
                return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
            return fn(**args)

    return DeepSeekAgent(
        cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        tool_runner=tool_runner,
        max_tool_rounds=cfg["max_tool_rounds"],
        max_tokens=cfg["max_tokens"],
        timeout_seconds=cfg["timeout_seconds"],
    )
