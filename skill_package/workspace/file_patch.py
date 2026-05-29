"""工作区文本文件片段替换（供各 skill 的 patch_* 工具复用）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def apply_text_replacement(
    text: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
    occurrence: int = 1,
) -> tuple[str, dict[str, Any]]:
    """将 text 中匹配的 old_string 替换为 new_string。"""
    if old_string == "":
        raise ValueError("old_string 不能为空；新建文件请使用 save_*_file 写入完整内容。")

    total = text.count(old_string)
    if total == 0:
        raise ValueError(
            "未在文件中找到 old_string。请先 read 该文件，并保证与原文完全一致（含空格、缩进、换行）。"
        )

    if replace_all:
        patched = text.replace(old_string, new_string)
        return patched, {
            "mode": "replace_all",
            "replacements": total,
            "total_matches": total,
        }

    occ = int(occurrence or 1)
    if occ < 1:
        raise ValueError("occurrence 须为大于等于 1 的整数。")
    if total < occ:
        raise ValueError(
            f"old_string 在文件中出现 {total} 次，无法替换第 {occ} 处；"
            f"请设置 replace_all=true 或调整 occurrence。"
        )
    if total > 1 and occ == 1:
        raise ValueError(
            f"old_string 在文件中出现 {total} 次（不唯一）。"
            f"请指定 occurrence（2..{total}）或 replace_all=true。"
        )

    start = 0
    idx = -1
    for _ in range(occ):
        idx = text.find(old_string, start)
        if idx == -1:
            raise ValueError(f"替换第 {occ} 处时未找到匹配。")
        start = idx + len(old_string)

    patched = text[:idx] + new_string + text[idx + len(old_string) :]
    return patched, {
        "mode": "single",
        "replacements": 1,
        "occurrence": occ,
        "total_matches": total,
    }


def patch_text_file(
    path: Path,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
    occurrence: int = 1,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}（新建请用 save_*_file）")

    original = path.read_text(encoding="utf-8")
    patched, meta = apply_text_replacement(
        original,
        old_string,
        new_string,
        replace_all=replace_all,
        occurrence=occurrence,
    )
    path.write_text(patched, encoding="utf-8")
    return {
        **meta,
        "bytes": path.stat().st_size,
        "chars_before": len(original),
        "chars_after": len(patched),
    }
