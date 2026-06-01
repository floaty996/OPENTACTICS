from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from pathlib import Path

from skill_package.core.skill import Skill

logger = logging.getLogger(__name__)

_SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
_CUSTOM_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "config" / "custom_skills"


class SkillPackageOrchestrator:
    """Scan system + custom skill dirs and load SKILL.md; tools register on import of tools subpackages.

    When ``allowed_skill_ids`` is set, only whitelisted skills are mounted, summarized, and activated
    (per-agent skill lists). When omitted, every skill under the roots is visible.
    """

    def __init__(
        self,
        root: str | Path | None = None,
        custom_root: str | Path | None = None,
        allowed_skill_ids: Iterable[str] | None = None,
    ):
        self.root = Path(root) if root is not None else _SKILLS_ROOT
        self.custom_root = Path(custom_root) if custom_root is not None else _CUSTOM_SKILLS_ROOT
        self._allowed: frozenset[str] | None = (
            frozenset(s.strip() for s in allowed_skill_ids if str(s).strip())
            if allowed_skill_ids is not None
            else None
        )
        self.skills: dict[str, Skill] = {}
        self.active_skill: Skill | None = None
        self._loaded_tool_packages: set[str] = set()
        self._discover()

    def refresh_skills(self) -> None:
        """Re-scan skills directories (call after adding a skill folder; no process restart)."""
        self._discover()

    def _discover(self) -> None:
        self.skills.clear()
        self._discover_root(self.root, "system")
        self._discover_root(self.custom_root, "custom")

    def _discover_root(self, root: Path, origin: str) -> None:
        if not root.exists():
            if origin == "custom":
                root.mkdir(parents=True, exist_ok=True)
            else:
                logger.warning("Skill root does not exist: %s", root)
            return
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            skill_id = d.name
            if skill_id in self.skills:
                continue
            if self._allowed is not None and skill_id not in self._allowed:
                continue
            self.skills[skill_id] = Skill(skill_id=skill_id, path=d, origin=origin)

    def ensure_tools_loaded(self, skill_id: str) -> bool:
        """Import skill_package.skills.<skill_id>.tools to trigger @register_skill_tool."""
        sk = self.skills.get(skill_id)
        if sk is None or sk.origin != "system":
            return False
        if skill_id in self._loaded_tool_packages:
            return True
        module_name = f"skill_package.skills.{skill_id}.tools"
        try:
            importlib.import_module(module_name)
            self._loaded_tool_packages.add(skill_id)
            return True
        except ModuleNotFoundError:
            logger.debug("Skill %s has no tools package (ok to skip)", skill_id)
            return False
        except Exception:
            logger.exception("Failed to load tools for skill: %s", skill_id)
            return False

    def ensure_all_visible_tools_loaded(self) -> None:
        """ensure_tools_loaded for every skill visible to this orchestrator."""
        for sid in self.skills:
            self.ensure_tools_loaded(sid)

    def activate(
        self,
        skill_id: str,
        *,
        execute_skill_blocks: bool = False,
        exec_timeout: float = 30.0,
    ) -> str | None:
        if skill_id not in self.skills:
            return None
        self.ensure_tools_loaded(skill_id)
        self.active_skill = self.skills[skill_id]
        context, _, _ = self.active_skill.get_full_context(
            execute_skill_blocks=execute_skill_blocks,
            exec_timeout=exec_timeout,
        )
        return context

    def get_skill_summary(self) -> str:
        if not self.skills:
            return "(No skills discovered)"
        lines: list[str] = []
        for sid, sk in self.skills.items():
            desc = sk.description.replace("\n", " ")
            if len(desc) > 120:
                desc = desc[:117] + "..."
            tag = "system" if sk.origin == "system" else "custom"
            lines.append(f"- **{sid}** ({sk.name}, {tag}): {desc}")
        return "\n".join(lines)


default_orchestrator = SkillPackageOrchestrator()
