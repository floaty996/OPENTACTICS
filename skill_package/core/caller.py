"""调用 Skill 的统一框架：加载 MD → 执行内嵌 Python → 拼回正文 → 交给智能体。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from skill_package.core.md_exec import RUN_PYTHON_LANG
from skill_package.core.orchestrator import SkillPackageOrchestrator, default_orchestrator
from skill_package.core.registry import get_tool_function, get_tool_schemas_for_skill

ToolRunner = Callable[[str, dict[str, Any]], str]


@dataclass
class SkillInvokeResult:
    """一次 skill 调用的完整产物，供智能体消费。"""

    skill_id: str
    context: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    raw_instructions: str = ""
    processed_instructions: str = ""
    block_outputs: list[str] = field(default_factory=list)

    def make_tool_runner(self) -> ToolRunner:
        """根据本 skill 已注册工具生成默认 tool_runner。"""

        def _run(name: str, arguments: dict[str, Any]) -> str:
            fn = get_tool_function(name)
            if fn is None:
                import json

                return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
            return fn(**arguments)

        return _run


class SkillCaller:
    """Skill 调用框架。

    典型流程::

        caller = SkillCaller()
        result = caller.invoke("database")
        agent.chat(result.context, user_question, tools=result.tools)

    ``run-python`` 块执行后，输出会**替换**该块出现在 ``result.context`` 中；
    原始 SKILL.md 文件不会被修改。
    """

    def __init__(
        self,
        orchestrator: SkillPackageOrchestrator | None = None,
        *,
        execute_blocks: bool = True,
        exec_timeout: float = 30.0,
        fence_lang: str = RUN_PYTHON_LANG,
    ):
        self.orchestrator = orchestrator or default_orchestrator
        self.execute_blocks = execute_blocks
        self.exec_timeout = exec_timeout
        self.fence_lang = fence_lang

    def invoke(self, skill_id: str) -> SkillInvokeResult:
        """加载 skill、执行 MD 内 Python 块、组装完整上下文与工具 schema。"""
        if skill_id not in self.orchestrator.skills:
            available = ", ".join(self.orchestrator.skills.keys()) or "（无）"
            raise ValueError(f"skill 不存在: {skill_id!r}，当前可用: {available}")

        skill = self.orchestrator.skills[skill_id]
        self.orchestrator.ensure_tools_loaded(skill_id)
        self.orchestrator.active_skill = skill

        raw = skill.instructions
        context, outputs, processed = skill.get_full_context(
            execute_skill_blocks=self.execute_blocks,
            exec_timeout=self.exec_timeout,
        )

        return SkillInvokeResult(
            skill_id=skill_id,
            context=context,
            tools=get_tool_schemas_for_skill(skill_id),
            raw_instructions=raw,
            processed_instructions=processed,
            block_outputs=outputs,
        )

    def invoke_for_agent(
        self,
        skill_id: str,
        user_message: str,
        *,
        agent: Any | None = None,
        tool_runner: ToolRunner | None = None,
    ) -> str:
        """invoke + 调用智能体，返回模型最终文本回复。

        ``agent`` 须实现 ``chat(context, user_message, tools=...)`` 且可迭代返回 str 片段；
        未传入时从 ``agents.get_agent_backend`` 懒加载。
        """
        result = self.invoke(skill_id)
        runner = tool_runner or result.make_tool_runner()

        if agent is None:
            from agents import get_agent_backend

            agent = get_agent_backend(tool_runner=runner)

        chunks: list[str] = []
        for chunk in agent.chat(result.context, user_message, tools=result.tools):
            chunks.append(chunk)
        return "".join(chunks)


default_skill_caller = SkillCaller()
