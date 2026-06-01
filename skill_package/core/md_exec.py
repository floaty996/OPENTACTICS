"""Extract and run explicitly tagged code blocks from Markdown; replace blocks with output in memory.

Convention (avoids running ordinary example code):
- Only fences whose first line is ``run-python`` are executed, e.g.::

    ```run-python
    print(1 + 1)
    ```

  After execution the fence in the agent context becomes plain output (e.g. ``2``).
  **Disk SKILL.md is never modified.**

Security: running arbitrary Python is equivalent to executing scripts on this machine.
Use only with trusted SKILL content, trusted environments, and explicit
``execute_skill_blocks``; prefer timeouts and read-only tasks.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Distinct from ```python examples; must say run-python to execute
RUN_PYTHON_LANG = "run-python"

_FENCE_RE = re.compile(
    r"^```([^\n`]+)\s*\n(.*?)^```\s*$",
    re.DOTALL | re.MULTILINE,
)


def iter_tagged_fences(markdown: str, fence_lang: str) -> list[str]:
    """Return code bodies for all fences tagged ``fence_lang`` (in document order)."""
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
    """Run code in a subprocess with the current interpreter; return stdout/stderr summary."""
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
    except Exception as e:  # pragma: no cover
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
    """Run each tagged block; return outputs in block order."""
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
    """Run tagged blocks and **replace** each fence with plain-text output (memory only).

    e.g. `` ```run-python\\nprint(3)\\n``` `` becomes ``3``.

    Returns ``(processed markdown, per-block output list)``.
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
