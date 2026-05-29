"""
database skill + DeepSeek 对话测试。

运行：
  1. 复制 config/deepseek.example.json 为 config/deepseek.json
  2. 在 deepseek.json 中填写 api_key
  3. pip install openai
  4. python database_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents import get_agent_backend  # noqa: E402
from skill_package import SkillCaller, get_tool_function  # noqa: E402

skill_caller = SkillCaller(execute_blocks=True)


def prepare_skill(skill_id: str) -> tuple[str, list[dict[str, Any]]]:
    """加载 skill：执行 run-python 块并用输出替换（不写回 MD）→ 返回智能体上下文与工具。"""
    result = skill_caller.invoke(skill_id)
    return result.context, result.tools


def _run_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = get_tool_function(name)
    if fn is None:
        return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
    return fn(**arguments)


def chat_gpt(question: str, skill: str) -> None:
    context, tools = prepare_skill(skill)
    agent = get_agent_backend(tool_runner=_run_tool)

    print("=" * 60)
    print(f"Skill: {skill} | 模型: {agent.model} | 工具数: {len(tools)}")
    print("=" * 60)
    print("开始对话...\n")

    for chunk in agent.chat(context, question, tools=tools):
        print(chunk, end="", flush=True)

    print("\n" + "=" * 60)
    print("对话完成！")


def main() -> None:
    question = (
        "我要做一个人力分析"
    )
    chat_gpt(question, skill="database")


if __name__ == "__main__":
    main()
