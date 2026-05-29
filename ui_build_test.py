"""
UI_build skill + DeepSeek 对话测试。

运行：
  1. 复制 config/deepseek.example.json 为 config/deepseek.json 并填写 api_key
  2. pip install openai
  3. python ui_build_test.py

可选：在下方 DB_CONFIG 中填写客户库连接，将写入 workspace/{db_alias}/config.json。
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

SKILL_ID = "UI_build"

skill_caller = SkillCaller(execute_blocks=True)

# 若用户已在对话中提供连接信息，可在此预填（password 写入 workspace/{db_alias}/config.json）
DB_CONFIG: dict[str, Any] | None = None
# 示例：
# DB_CONFIG = {
#     "db_alias": "customer_acme",
#     "db_type": "mysql",
#     "host": "127.0.0.1",
#     "port": 3306,
#     "user": "readonly",
#     "password": "your-password",
#     "database": "biz_db",
# }


def prepare_skill(skill_id: str = SKILL_ID) -> tuple[str, list[dict[str, Any]]]:
    """加载 skill：执行 run-python 块 → 返回智能体上下文与工具 schema。"""
    result = skill_caller.invoke(skill_id)
    return result.context, result.tools


def _run_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = get_tool_function(name)
    if fn is None:
        return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
    return fn(**arguments)


def _build_question(user_question: str) -> str:
    if not DB_CONFIG:
        return user_question
    alias = DB_CONFIG.get("db_alias", "")
    extra = (
        f"\n\n【系统附带的库连接信息】请先调用 save_database_config 落盘，db_alias={alias!r}：\n"
        f"{json.dumps(DB_CONFIG, ensure_ascii=False, indent=2)}\n"
        "落盘后再 check_db_connected_frontend，按 SKILL 流程生成或迭代前端。"
    )
    return user_question + extra


def chat_gpt(question: str, skill: str = SKILL_ID) -> None:
    context, tools = prepare_skill(skill)
    agent = get_agent_backend(tool_runner=_run_tool)
    full_question = _build_question(question)

    print("=" * 60)
    print(f"Skill: {skill} | 模型: {agent.model} | 工具数: {len(tools)}")
    if DB_CONFIG:
        print(f"已附带 DB 配置: db_alias={DB_CONFIG.get('db_alias')}")
    print("=" * 60)
    print("开始对话...\n")

    for chunk in agent.chat(context, full_question, tools=tools):
        print(chunk, end="", flush=True)

    print("\n" + "=" * 60)
    print("对话完成！")


def main() -> None:
    question = (
        "请按 UI_build skill 的流程处理："
        "1) 先 list_ui_assets 与 check_db_connected_frontend（db_alias 若未知向我确认）；"
        "2) 若没有接库前端则新建 React+Vite 管理页脚手架到 assets 对应目录；"
        "3) 说明 workspace 路径与本地启动方式。"
        "db_alias 若未知请先向我确认；表结构可读 workspace/{db_alias}/dataset/。"
    )
    chat_gpt(question)


if __name__ == "__main__":
    main()
