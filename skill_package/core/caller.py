"""Unified skill invocation: load MD → run embedded Python → merge body → hand off to agent."""

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
    """Full output of one skill invocation for the agent."""

    skill_id: str
    context: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    raw_instructions: str = ""
    processed_instructions: str = ""
    block_outputs: list[str] = field(default_factory=list)

    def make_tool_runner(self) -> ToolRunner:
        """Build default tool_runner from tools registered for this skill."""

        def _run(name: str, arguments: dict[str, Any]) -> str:
            fn = get_tool_function(name)
            if fn is None:
                import json

                return json.dumps({"ok": False, "error": f"Unknown tool: {name}"}, ensure_ascii=False)
            return fn(**arguments)

        return _run


class SkillCaller:
    """Skill invocation framework.

    Typical flow::

        caller = SkillCaller()
        result = caller.invoke("database")
        agent.chat(result.context, user_question, tools=result.tools)

    After ``run-python`` blocks run, their output **replaces** the fence in ``result.context``;
    the on-disk SKILL.md file is unchanged.
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
        """Load skill, run MD Python blocks, assemble context and tool schemas."""
        if skill_id not in self.orchestrator.skills:
            available = ", ".join(self.orchestrator.skills.keys()) or "(none)"
            raise ValueError(f"Unknown skill: {skill_id!r}; available: {available}")

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
        """invoke + call agent; return final model text.

        ``agent`` must implement ``chat(context, user_message, tools=...)`` yielding str chunks;
        if omitted, loads from ``agents.get_agent_backend``.
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
