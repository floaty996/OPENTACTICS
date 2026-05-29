from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 執行環境若無 PyYAML 則用簡易解析
    yaml = None  # type: ignore


def _parse_simple_frontmatter(block: str) -> dict:
    """仅支持`key: value`格式，作为无PyYAML时的备用方案"""
    out: dict = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        val = rest.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


class Skill:
    """单一技能：对应目录中的SKILL.md文件以及可选的tools/目录"""

    def __init__(self, skill_id: str, path: str | Path, *, origin: str = "system"):
        self.skill_id = skill_id
        self.path = Path(path).resolve()
        self.origin = origin if origin in ("system", "custom") else "system"
        self.skill_file = self.path / "SKILL.md"
        self.metadata: dict = {}
        self.instructions = ""
        self._load()

    def _load(self) -> None:
        if not self.skill_file.exists():
            self.metadata = {"name": self.skill_id}
            self.instructions = "（尚未提供 SKILL.md）"
            return
        try:
            content = self.skill_file.read_text(encoding="utf-8")
            if content.lstrip().startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    raw_fm = parts[1]
                    if yaml is not None:
                        fm = yaml.safe_load(raw_fm) or {}
                    else:
                        fm = _parse_simple_frontmatter(raw_fm)
                    self.metadata = fm if isinstance(fm, dict) else {}
                    self.instructions = parts[2].strip()
                    return
            self.metadata = {"name": self.skill_id}
            self.instructions = content.strip()
        except Exception:
            self.metadata = {"name": self.skill_id}
            self.instructions = "SKILL.md 获取失敗。"

    @property
    def name(self) -> str:
        return str(self.metadata.get("name", self.skill_id))

    @property
    def description(self) -> str:
        return str(self.metadata.get("description", ""))

    @property
    def read_only(self) -> bool:
        if self.origin == "system":
            return True
        return bool(self.metadata.get("read_only"))

    def get_file_tree(self) -> str:
        lines: list[str] = []
        for root, _dirs, files in os.walk(self.path):
            if Path(root).name == "generated":
                continue
            rel = Path(root).relative_to(self.path)
            level = len(rel.parts) if str(rel) != "." else 0
            indent = "  " * level
            lines.append(f"{indent}📂 {root}/")
            sub = "  " * (level + 1)
            for f in sorted(files):
                if f == "SKILL.md":
                    continue
                lines.append(f"{sub}📄 {os.path.join(root, f)}")
        return "\n".join(lines)

    def prepare_instructions(
        self,
        *,
        execute_skill_blocks: bool = False,
        exec_timeout: float = 30.0,
    ) -> tuple[str, list[str]]:
        """处理 SKILL 正文：执行 ``run-python`` 块，用输出替换原围栏（仅内存，不写回文件）。

        返回 ``(处理后的正文, 各块输出列表)``。
        """
        if not execute_skill_blocks:
            return self.instructions, []
        from skill_package.core.md_exec import execute_and_inject_outputs

        return execute_and_inject_outputs(
            self.instructions,
            cwd=self.path,
            timeout=exec_timeout,
        )

    def get_full_context(
        self,
        *,
        execute_skill_blocks: bool = False,
        exec_timeout: float = 30.0,
    ) -> tuple[str, list[str], str]:
        """组装给模型看的 skill 上下文。

        若 ``execute_skill_blocks=True``，会先执行正文中 ``run-python`` 围栏块，
        用纯文本输出替换各块（磁盘上的 SKILL.md 不变），再与附加 MD、目录结构一并返回。

        返回 ``(完整上下文, 各块输出列表, 处理后的 SKILL 正文)``。
        """
        instructions_body, block_outputs = self.prepare_instructions(
            execute_skill_blocks=execute_skill_blocks,
            exec_timeout=exec_timeout,
        )
        parts = [
            f"# Active Skill: {self.name}",
            "## 1. Instructions",
            instructions_body,
        ]
        section_no = 2

        md_extra: list[str] = []
        for md_file in sorted(self.path.rglob("*.md")):
            if md_file.name == "SKILL.md":
                continue
            rel = md_file.relative_to(self.path)
            text = md_file.read_text(encoding="utf-8")
            if execute_skill_blocks:
                from skill_package.core.md_exec import execute_and_inject_outputs

                text, _ = execute_and_inject_outputs(
                    text,
                    cwd=md_file.parent,
                    timeout=exec_timeout,
                )
            md_extra.append(f"\n### {rel}\n{text}")
        if md_extra:
            parts.append(f"\n## {section_no}. Additional markdown")
            parts.extend(md_extra)
            section_no += 1
        parts.append(f"\n## {section_no}. Layout")
        parts.append(f"```text\n{self.get_file_tree()}\n```")
        return "\n\n".join(parts), block_outputs, instructions_body
