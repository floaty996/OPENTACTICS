"""从 Markdown 中抽取并执行「显式标记」的代码块，用执行输出替换块内容（仅内存）。

约定（避免误执行普通示例代码）：
- 仅识别围栏第一行为 ``run-python`` 的代码块，例如::

    ```run-python
    print(1 + 1)
    ```

  执行后传给智能体的正文中，该围栏会被替换为纯文本输出（如 ``2``），
  **不会**改写磁盘上的 SKILL.md。

安全说明：执行任意 Python 等同于在本机运行脚本，存在数据外泄与破坏风险。
仅应在可信 SKILL、可信环境、且明确开启 ``execute_skill_blocks`` 时使用，并建议配合超时与只读任务。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 与常见 ```python 示例区分，必须显式写 run-python 才会执行
RUN_PYTHON_LANG = "run-python"

_FENCE_RE = re.compile(
    r"^```([^\n`]+)\s*\n(.*?)^```\s*$",
    re.DOTALL | re.MULTILINE,
)


def iter_tagged_fences(markdown: str, fence_lang: str) -> list[str]:
    """返回正文中所有语言标记为 ``fence_lang`` 的代码块内容（按出现顺序）。"""
    want = fence_lang.strip().lower()
    out: list[str] = []
    for lang, body in _FENCE_RE.findall(markdown):
        if lang.strip().lower() == want:
            code = body.rstrip("\n")
            if code.strip():
                out.append(code)
    return out


def run_python_snippet(
    code: str,
    *,
    cwd: Path | None = None,
    timeout: float = 30.0,
) -> str:
    """用当前解释器在子进程中执行代码，返回 stdout/stderr 与退出码摘要。"""
    fd, path = tempfile.mkstemp(suffix="_skill_exec.py", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        proc = subprocess.run(
            [sys.executable, path],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        parts: list[str] = []
        if proc.stdout:
            parts.append(proc.stdout.rstrip("\n"))
        if proc.stderr:
            parts.append("[stderr]\n" + proc.stderr.rstrip("\n"))
        if proc.returncode != 0:
            parts.append(f"[exit code {proc.returncode}]")
        return "\n".join(parts) if parts else "(no output)"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as e:  # pragma: no cover - 极端环境
        return f"[execution error] {e!s}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def collect_run_python_outputs(
    markdown: str,
    *,
    cwd: Path | None = None,
    timeout: float = 30.0,
    fence_lang: str = RUN_PYTHON_LANG,
) -> list[str]:
    """对每个标记块依次执行，返回与块顺序一致的输出文本列表。"""
    return [
        run_python_snippet(block, cwd=cwd, timeout=timeout)
        for block in iter_tagged_fences(markdown, fence_lang)
    ]


def execute_and_inject_outputs(
    markdown: str,
    *,
    cwd: Path | None = None,
    timeout: float = 30.0,
    fence_lang: str = RUN_PYTHON_LANG,
) -> tuple[str, list[str]]:
    """执行标记代码块，用纯文本输出**替换**原围栏（不修改源文件，仅内存结果）。

    例如 `` ```run-python\\nprint(3)\\n``` `` 变为 ``3``。

    返回 ``(处理后的 markdown, 各块输出列表)``。
    """
    want = fence_lang.strip().lower()
    outputs: list[str] = []
    pieces: list[str] = []
    last = 0

    for match in _FENCE_RE.finditer(markdown):
        lang, body = match.group(1), match.group(2)
        pieces.append(markdown[last : match.start()])

        if lang.strip().lower() == want and body.strip():
            code = body.rstrip("\n")
            output = run_python_snippet(code, cwd=cwd, timeout=timeout)
            outputs.append(output)
            pieces.append(output.rstrip("\n"))
        else:
            pieces.append(match.group(0))

        last = match.end()

    pieces.append(markdown[last:])
    return "".join(pieces), outputs
