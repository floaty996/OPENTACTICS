"""用户自定义 Skill 存储（config/custom_skills/）。"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from skill_package.core.orchestrator import _CUSTOM_SKILLS_ROOT

_SKILL_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_TEXT_SUFFIXES = {
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
}


def custom_skills_root() -> Path:
    root = _CUSTOM_SKILLS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_skill_id(skill_id: str) -> str:
    sid = str(skill_id or "").strip()
    if not _SKILL_ID_RE.match(sid):
        raise ValueError(
            "skill_id 须以字母开头，仅含字母、数字、下划线、连字符，最长 64 字符"
        )
    if sid.startswith("_"):
        raise ValueError("skill_id 不能以 _ 开头")
    return sid


def sanitize_skill_id(raw: str) -> str:
    """将文件夹名等转为合法 skill_id（中文/空格会转成下划线并加 skill_ 前缀）。"""
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        raise ValueError("无法从文件夹名生成 skill_id，请使用英文字母开头的目录名")
    if not re.match(r"^[A-Za-z]", s):
        s = f"skill_{s}"
    if len(s) > 64:
        s = s[:64].rstrip("_")
    return validate_skill_id(s)


def iter_custom_skill_dirs() -> list[Path]:
    """磁盘上所有含 SKILL.md 的自定义 skill 目录。"""
    root = custom_skills_root()
    if not root.is_dir():
        return []
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    )


def skill_dir(skill_id: str) -> Path:
    sid = validate_skill_id(skill_id)
    return custom_skills_root() / sid


def _parse_skill_id_from_skill_md(content: str) -> str | None:
    try:
        import yaml
    except ImportError:
        yaml = None  # type: ignore
    if not content.lstrip().startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    raw = parts[1]
    meta: dict[str, Any] = {}
    if yaml is not None:
        loaded = yaml.safe_load(raw) or {}
        if isinstance(loaded, dict):
            meta = loaded
    name = str(meta.get("name") or "").strip()
    if name and _SKILL_ID_RE.match(name):
        return name
    return None


def write_custom_skill_file(skill_id: str, rel_path: str, content: str) -> dict[str, Any]:
    sid = validate_skill_id(skill_id)
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError(f"非法文件路径: {rel_path!r}")
    root = skill_dir(sid)
    target = (root / rel).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError("文件路径须位于 skill 目录内")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"skill_id": sid, "path": rel, "size": target.stat().st_size}


def create_custom_skill(
    skill_id: str,
    *,
    name: str = "",
    description: str = "",
    instructions: str = "",
    skill_md: str = "",
) -> dict[str, Any]:
    sid = validate_skill_id(skill_id)
    root = skill_dir(sid)
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"自定义 skill 已存在: {sid}")
    root.mkdir(parents=True, exist_ok=True)
    if skill_md.strip():
        content = skill_md.strip() + "\n"
    else:
        nm = name.strip() or sid
        desc = description.strip() or f"用户自定义 Skill：{nm}"
        body = instructions.strip() or "## 使用说明\n\n（请补充 Skill 指令正文）\n"
        content = (
            "---\n"
            f"name: {nm}\n"
            f"description: >-\n  {desc.replace(chr(10), ' ')}\n"
            "origin: custom\n"
            "studio_visible: true\n"
            "---\n\n"
            f"{body}\n"
        )
    (root / "SKILL.md").write_text(content, encoding="utf-8")
    return {"skill_id": sid, "path": str(root), "created": True}


def delete_custom_skill(skill_id: str) -> dict[str, Any]:
    sid = validate_skill_id(skill_id)
    root = skill_dir(sid)
    if not root.exists():
        raise FileNotFoundError(f"自定义 skill 不存在: {sid}")
    shutil.rmtree(root)
    return {"skill_id": sid, "deleted": True}


def _skill_import_prefix(skill_md_rel: str) -> str:
    prefix = str(Path(skill_md_rel).parent)
    if prefix in (".", ""):
        return ""
    return prefix


def _resolve_import_skill_id(
    skill_md_text: str,
    skill_md_rel: str,
    *,
    skill_id: str | None = None,
    path_hints: list[str] | None = None,
) -> str:
    sid = (skill_id or "").strip() or None
    if sid:
        return validate_skill_id(sid)
    sid = _parse_skill_id_from_skill_md(skill_md_text)
    if sid:
        return validate_skill_id(sid)
    base = Path(skill_md_rel).parent.name
    if base and base not in (".", ""):
        try:
            return sanitize_skill_id(base)
        except ValueError:
            pass
    for hint in path_hints or []:
        part = str(hint).replace("\\", "/").split("/")[0]
        if not part:
            continue
        try:
            return sanitize_skill_id(part)
        except ValueError:
            continue
    raise ValueError(
        "无法确定 skill_id：请让文件夹名以英文字母开头（如 my_skill），"
        "或在 SKILL.md 的 name 字段填写合法 id（字母开头，仅含字母数字_-）"
    )


def _rel_under_skill_prefix(name: str, prefix: str) -> str | None:
    name = name.replace("\\", "/").lstrip("/")
    if not name or name.endswith("/"):
        return None
    if ".." in Path(name).parts:
        return None
    if prefix and name.startswith(prefix + "/"):
        return name[len(prefix) + 1 :]
    if prefix and name == prefix + "/SKILL.md":
        return "SKILL.md"
    if not prefix:
        return name
    return None


def import_custom_skill_files(
    entries: list[tuple[str, bytes]],
    *,
    skill_id: str | None = None,
) -> dict[str, Any]:
    """从文件夹上传的多文件列表导入自定义 Skill（paths 为相对 skill 根的路径）。"""
    if not entries:
        raise ValueError("未选择任何文件")
    total = sum(len(data) for _, data in entries)
    if total > _MAX_UPLOAD_BYTES:
        raise ValueError(f"文件夹过大（>{_MAX_UPLOAD_BYTES // (1024 * 1024)}MB）")

    normalized: list[tuple[str, bytes]] = []
    for rel, data in entries:
        rel = str(rel or "").replace("\\", "/").lstrip("/")
        if not rel or rel.endswith("/"):
            continue
        if "__MACOSX" in rel or rel.endswith(".DS_Store"):
            continue
        if ".." in Path(rel).parts:
            continue
        normalized.append((rel, data))

    if not normalized:
        raise ValueError("未包含有效文件")

    skill_md_entries = [(r, d) for r, d in normalized if Path(r).name == "SKILL.md"]
    if not skill_md_entries:
        raise ValueError("文件夹须包含 SKILL.md")

    skill_md_rel, skill_md_bytes = min(skill_md_entries, key=lambda x: x[0].count("/"))
    skill_md_text = skill_md_bytes.decode("utf-8", errors="replace")
    prefix = _skill_import_prefix(skill_md_rel)
    sid = _resolve_import_skill_id(
        skill_md_text,
        skill_md_rel,
        skill_id=skill_id,
        path_hints=[r for r, _ in normalized],
    )

    dest = skill_dir(sid)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    written = 0
    for rel, data in normalized:
        out_rel = _rel_under_skill_prefix(rel, prefix)
        if not out_rel:
            continue
        target = (dest / out_rel).resolve()
        if dest.resolve() not in target.parents and target != dest.resolve():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1

    if written == 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("未能写入任何文件，请确认选择了完整的 skill 文件夹")

    return {"skill_id": sid, "path": str(dest), "uploaded": True, "file_count": written}


def extract_custom_skill_zip(data: bytes, *, skill_id: str | None = None) -> dict[str, Any]:
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValueError(f"压缩包过大（>{_MAX_UPLOAD_BYTES // (1024 * 1024)}MB）")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [i for i in zf.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX")]
        if not members:
            raise ValueError("压缩包为空")
        skill_md_members = [m for m in members if Path(m.filename).name == "SKILL.md"]
        if not skill_md_members:
            raise ValueError("压缩包须包含 SKILL.md")
        entries = [
            (m.filename.replace("\\", "/"), zf.read(m))
            for m in members
            if not m.filename.endswith("/")
        ]
    return import_custom_skill_files(entries, skill_id=skill_id)


def list_custom_skill_ids() -> list[str]:
    root = custom_skills_root()
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()
    )


def read_text_file(path: Path, *, max_bytes: int = 512_000) -> str:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"文件过大（>{max_bytes // 1024}KB）")
    if path.suffix.lower() not in _TEXT_SUFFIXES and path.name != "SKILL.md":
        raise ValueError(f"不支持的文件类型: {path.suffix}")
    return path.read_text(encoding="utf-8", errors="replace")


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
