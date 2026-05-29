"""
Skill 调用框架示例。

流程：读取 SKILL.md → 执行 run-python 块 → 用输出替换块（仅内存）→ 传给智能体。

  python skill_invoke_example.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents import get_agent_backend  # noqa: E402
from skill_package import SkillCaller  # noqa: E402


def main() -> None:
    caller = SkillCaller(execute_blocks=True)
    skill_id = "database"
    question = "简要说明本 skill 能做什么。"

    result = caller.invoke(skill_id)
    print("=" * 60)
    print(f"Skill: {skill_id}")
    print(f"run-python 块数: {len(result.block_outputs)}")
    print(f"工具数: {len(result.tools)}")
    print("=" * 60)

    if result.block_outputs:
        print("\n各块执行输出预览:")
        for i, out in enumerate(result.block_outputs, 1):
            preview = out[:200] + ("..." if len(out) > 200 else "")
            print(f"  Block {i}: {preview}")

    agent = get_agent_backend(tool_runner=result.make_tool_runner())
    print("\n智能体回复:\n")
    for chunk in agent.chat(result.context, question, tools=result.tools):
        print(chunk, end="", flush=True)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
