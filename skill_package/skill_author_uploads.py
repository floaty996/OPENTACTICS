"""Skill 创建助手：用户上传参考文件与会话目录。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_UPLOADS_ROOT = _ROOT / "config" / "skill_author_uploads"
_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_FILES_PER_SESSION = 20
_ALLOWED_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".csv",
    ".pdf",
    ".doc",
    ".docx",
}
_SESSION_RE = re.compile(r"^[a-f0-9]{8,32}$")


def _uploads_root() -> Path:
    _UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    return _UPLOADS_ROOT


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def validate_session_id(session_id: str) -> str:
    sid = str(session_id or "").strip().lower()
    if not _SESSION_RE.match(sid):
        raise ValueError("无效的 skill_author 会话 id")
    return sid


def session_dir(session_id: str) -> Path:
    sid = validate_session_id(session_id)
    d = _uploads_root() / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(session_id: str, filename: str, data: bytes) -> dict[str, Any]:
    sid = validate_session_id(session_id)
    name = Path(str(filename or "").strip()).name
    if not name:
        raise ValueError("文件名为空")
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ValueError(f"不支持的文件类型: {suffix or '（无扩展名）'}")
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError(f"单文件过大（>{_MAX_FILE_BYTES // (1024 * 1024)}MB）")
    folder = session_dir(sid)
    existing = [p for p in folder.iterdir() if p.is_file()]
    if len(existing) >= _MAX_FILES_PER_SESSION:
        raise ValueError(f"每个会话最多上传 {_MAX_FILES_PER_SESSION} 个文件")
    safe = re.sub(r"[^\w.\-]+", "_", name)[:120] or "file"
    target = folder / safe
    if target.exists():
        stem = target.stem
        target = folder / f"{stem}_{uuid.uuid4().hex[:6]}{target.suffix}"
    target.write_bytes(data)
    return {
        "session_id": sid,
        "filename": target.name,
        "size": target.stat().st_size,
        "suffix": suffix,
    }


def list_uploads(session_id: str) -> list[dict[str, Any]]:
    folder = session_dir(session_id)
    out: list[dict[str, Any]] = []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        out.append(
            {
                "filename": p.name,
                "size": p.stat().st_size,
                "suffix": p.suffix.lower(),
            }
        )
    return out


def read_upload(session_id: str, filename: str, *, max_bytes: int = 200_000) -> str:
    folder = session_dir(session_id)
    name = Path(str(filename or "").strip()).name
    path = (folder / name).resolve()
    if folder.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(f"文件不存在: {filename}")
    size = path.stat().st_size
    if size > max_bytes:
        return f"（文件 {name} 过大，{size} 字节，请让用户精简后重传）"
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return f"（已上传 PDF：{name}，{size} 字节；当前环境无法解析正文，请根据文件名引导用户补充文字说明）"
    if suffix in {".doc", ".docx"}:
        return f"（已上传 Word：{name}，{size} 字节；当前环境无法解析正文，请根据文件名引导用户补充文字说明）"
    return path.read_text(encoding="utf-8", errors="replace")


def build_upload_context(session_id: str | None) -> str:
    if not session_id:
        return ""
    try:
        files = list_uploads(session_id)
    except ValueError:
        return ""
    if not files:
        return ""
    names = ", ".join(f["filename"] for f in files)
    return (
        f"\n【Skill 创建参考文件】当前会话已上传 {len(files)} 个文件：{names}。"
        "需要内容时请调用 list_skill_author_uploads / read_skill_author_upload。\n"
    )
