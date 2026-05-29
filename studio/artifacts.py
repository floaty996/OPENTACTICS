"""工作区 skill 产物（dataset/、frontend/）列举与读写。"""

from __future__ import annotations

import mimetypes
import re
import shutil
from pathlib import Path
from typing import Any

from skill_package.workspace.paths import (
    backend_dir,
    dataset_dir,
    frontend_dir,
    read_manifest,
    touch_manifest,
    validate_db_alias,
    workspace_dir,
)

ARTIFACT_ROOTS = ("dataset", "frontend", "backend")
IGNORE_DIR_NAMES = {
    ".git",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".cache",
}
TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
    ".scss",
    ".less",
    ".html",
    ".htm",
    ".xml",
    ".yaml",
    ".yml",
    ".sql",
    ".env",
    ".example",
    ".sh",
    ".bat",
    ".py",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".svg",
    ".gitignore",
    ".editorconfig",
    ".prettierrc",
    ".log",
}
MAX_FILE_BYTES = 2 * 1024 * 1024

_FRONTMATTER_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n)?")
_YAML_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$")


def _normalize_rel_path(path: str) -> str:
    p = path.strip().replace("\\", "/").lstrip("/")
    if not p:
        raise ValueError("path 不能为空")
    if ".." in p.split("/"):
        raise ValueError("path 非法")
    parts = p.split("/")
    if parts[0] not in ARTIFACT_ROOTS:
        raise ValueError(f"path 须以 {' 或 '.join(ARTIFACT_ROOTS)} 开头")
    return p


def resolve_artifact_file(db_alias: str, rel_path: str) -> Path:
    alias = validate_db_alias(db_alias)
    rel = _normalize_rel_path(rel_path)
    root = workspace_dir(alias)
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("path 超出工作区")
    return target


_DOTFILE_ALLOW = {".gitignore", ".editorconfig", ".prettierrc", ".env", ".env.example"}


def _is_artifact_tree_path(rel_prefix: str) -> bool:
    p = rel_prefix.replace("\\", "/").strip("/")
    if p in ARTIFACT_ROOTS:
        return True
    return any(p.startswith(f"{root}/") for root in ARTIFACT_ROOTS)


def _should_skip_dir_entry(name: str, *, in_tree: bool) -> bool:
    if in_tree:
        return name in {"node_modules", ".git", ".svn"}
    return name in IGNORE_DIR_NAMES or name.startswith(".")


def _should_skip_entry(entry: Path, rel_prefix: str = "") -> bool:
    name = entry.name
    in_tree = _is_artifact_tree_path(rel_prefix)
    if entry.is_dir():
        return _should_skip_dir_entry(name, in_tree=in_tree)
    if name in _DOTFILE_ALLOW:
        return False
    if in_tree:
        return False
    return name.startswith(".")


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if not path.suffix and path.name in {".gitignore", ".editorconfig", "Dockerfile"}:
        return True
    mime, _ = mimetypes.guess_type(path.name)
    return bool(mime and mime.startswith("text/"))


def _dir_node(root: Path, rel_prefix: str) -> dict[str, Any] | None:
    if not root.is_dir():
        return None
    children: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return {"name": root.name, "path": rel_prefix, "type": "dir", "children": []}
    for entry in entries:
        if _should_skip_entry(entry, rel_prefix):
            continue
        rel = f"{rel_prefix}/{entry.name}" if rel_prefix else entry.name
        if entry.is_dir():
            child = _dir_node(entry, rel)
            if child:
                children.append(child)
        elif entry.is_file():
            children.append(
                {
                    "name": entry.name,
                    "path": rel,
                    "type": "file",
                    "size": entry.stat().st_size,
                    "editable": _is_text_file(entry),
                }
            )
    return {"name": root.name, "path": rel_prefix, "type": "dir", "children": children}


def _unquote_yaml_value(raw: str) -> str:
    val = raw.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        return val[1:-1]
    return val


def parse_simple_yaml(yaml_text: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    order: list[str] = []
    for line in yaml_text.splitlines():
        m = _YAML_LINE_RE.match(line.strip())
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2)
        fields[key] = _unquote_yaml_value(raw_val)
        order.append(key)
    return fields, order


def split_markdown_frontmatter(content: str) -> tuple[dict[str, str] | None, list[str], str]:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None, [], content
    fields, order = parse_simple_yaml(m.group(1))
    return fields, order, content[m.end() :]


def serialize_markdown_frontmatter(
    fields: dict[str, str],
    order: list[str] | None = None,
) -> str:
    keys: list[str] = []
    if order:
        keys.extend(k for k in order if k in fields)
    for k in fields:
        if k not in keys:
            keys.append(k)
    lines: list[str] = ["---"]
    for key in keys:
        val = str(fields[key])
        if re.search(r'[:#\n"]', val) or "," in val:
            escaped = val.replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def enforce_dataset_frontmatter_db_alias(db_alias: str, rel_path: str, content: str) -> str:
    rel = rel_path.replace("\\", "/")
    is_dataset_md = rel.startswith("dataset/") and rel.lower().endswith(".md")
    is_ui_knowledge = rel.lower().endswith("/ui_knowledge.md")
    is_api_knowledge = rel.lower().endswith("/api_knowledge.md")
    if not is_dataset_md and not is_ui_knowledge and not is_api_knowledge:
        return content
    fields, order, body = split_markdown_frontmatter(content)
    if fields is None:
        return content
    fields["db_alias"] = validate_db_alias(db_alias)
    if "db_alias" not in order:
        order.insert(0, "db_alias")
    return serialize_markdown_frontmatter(fields, order) + body


def list_artifact_tree(db_alias: str) -> dict[str, Any]:
    """仅展示磁盘上实际存在的 dataset / frontend / backend 目录及其内容。"""
    alias = validate_db_alias(db_alias)
    roots: list[dict[str, Any]] = []
    for name, getter in (
        ("dataset", dataset_dir),
        ("frontend", frontend_dir),
        ("backend", backend_dir),
    ):
        dir_path = getter(alias)
        if not dir_path.is_dir():
            continue
        node = _dir_node(dir_path, name)
        if node:
            roots.append(node)
    return {"db_alias": alias, "roots": roots}


def read_artifact(db_alias: str, rel_path: str) -> dict[str, Any]:
    path = resolve_artifact_file(db_alias, rel_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"文件过大（>{MAX_FILE_BYTES // 1024 // 1024}MB），请在本地编辑器打开")
    if not _is_text_file(path):
        raise ValueError("该文件类型不支持在线编辑，请在本地打开")
    content = path.read_text(encoding="utf-8")
    return {
        "path": rel_path.replace("\\", "/"),
        "content": content,
        "size": size,
        "editable": True,
    }


_ARTIFACT_ROOT_DIRS = frozenset(ARTIFACT_ROOTS)


def _artifact_root_name(rel: str) -> str | None:
    """path 为 dataset / frontend / backend 根目录时返回目录名（兼容末尾斜杠）。"""
    p = rel.replace("\\", "/").strip("/")
    parts = [x for x in p.split("/") if x]
    if len(parts) == 1 and parts[0] in _ARTIFACT_ROOT_DIRS:
        return parts[0]
    return None


def _is_artifact_root_dir(rel: str) -> bool:
    return _artifact_root_name(rel) is not None


def _after_artifact_root_delete(db_alias: str, root_name: str) -> None:
    if root_name == "dataset":
        touch_manifest(db_alias, knowledge_files=[])
    elif root_name == "frontend":
        touch_manifest(db_alias, projects=[])
    elif root_name == "backend":
        touch_manifest(db_alias, backend_projects=[])


def _sync_frontend_project_meta(db_alias: str, rel_path: str) -> None:
    rel = rel_path.replace("\\", "/")
    if not rel.startswith("frontend/"):
        return
    parts = rel.split("/")
    if len(parts) < 3:
        return
    project_name = parts[1]
    try:
        from skill_package.skills.UI_build.scripts.ui_assets import (
            _project_root,
            _read_manifest_file,
            _sync_project_manifest,
        )

        proj = _project_root(db_alias, project_name)
        if proj.is_dir():
            _sync_project_manifest(db_alias, project_name, _read_manifest_file(proj))
    except (ValueError, ImportError, OSError):
        pass


def _remove_dataset_knowledge_manifest(db_alias: str, rel: str) -> None:
    if not rel.startswith("dataset/") or not rel.lower().endswith(".md"):
        return
    manifest = read_manifest(db_alias)
    entry = rel if rel.startswith("dataset/") else f"dataset/{rel}"
    files = [f for f in (manifest.get("knowledge_files") or []) if f != entry]
    touch_manifest(db_alias, knowledge_files=files)


def _remove_dataset_md_manifests_under(db_alias: str, dir_path: Path) -> None:
    root = workspace_dir(db_alias)
    for md in dir_path.rglob("*.md"):
        if md.is_file():
            try:
                rel = md.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            _remove_dataset_knowledge_manifest(db_alias, rel)


def _sync_backend_project_meta(db_alias: str, rel_path: str) -> None:
    rel = rel_path.replace("\\", "/")
    if not rel.startswith("backend/"):
        return
    parts = rel.split("/")
    if len(parts) < 3:
        return
    project_name = parts[1]
    try:
        from skill_package.skills.backend.scripts.backend_assets import (
            _project_root,
            _read_manifest_file,
            _sync_backend_manifest,
        )

        proj = _project_root(db_alias, project_name)
        if proj.is_dir():
            _sync_backend_manifest(db_alias, project_name, _read_manifest_file(proj))
    except (ValueError, ImportError, OSError):
        pass


def _after_backend_delete(db_alias: str, rel: str) -> None:
    if not rel.startswith("backend/"):
        return
    parts = rel.split("/")
    if len(parts) < 2:
        return
    project_name = parts[1]
    try:
        from skill_package.skills.backend.scripts.backend_assets import (
            _project_root,
            _read_manifest_file,
            _sync_backend_manifest,
        )

        proj = _project_root(db_alias, project_name)
        if proj.is_dir():
            _sync_backend_manifest(db_alias, project_name, _read_manifest_file(proj))
        else:
            manifest = read_manifest(db_alias)
            projects = [
                p
                for p in (manifest.get("backend_projects") or [])
                if p.get("name") != project_name
            ]
            touch_manifest(db_alias, backend_projects=projects)
    except (ValueError, ImportError, OSError):
        pass


def _after_frontend_delete(db_alias: str, rel: str) -> None:
    if not rel.startswith("frontend/"):
        return
    parts = rel.split("/")
    if len(parts) < 2:
        return
    project_name = parts[1]
    try:
        from skill_package.skills.UI_build.scripts.ui_assets import (
            _project_root,
            _read_manifest_file,
            _sync_project_manifest,
        )

        proj = _project_root(db_alias, project_name)
        if proj.is_dir():
            _sync_project_manifest(db_alias, project_name, _read_manifest_file(proj))
        else:
            manifest = read_manifest(db_alias)
            projects = [
                p
                for p in (manifest.get("projects") or [])
                if p.get("name") != project_name
            ]
            touch_manifest(db_alias, projects=projects)
    except (ValueError, ImportError, OSError):
        pass


def create_artifact(db_alias: str, rel_path: str, content: str = "") -> dict[str, Any]:
    path = resolve_artifact_file(db_alias, rel_path)
    if path.exists():
        raise ValueError(f"文件已存在: {rel_path}")
    if path.suffix and not _is_text_file(path):
        raise ValueError("该文件类型不支持在线创建，请使用文本类扩展名")
    rel = rel_path.replace("\\", "/")
    body = enforce_dataset_frontmatter_db_alias(db_alias, rel, content or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if rel.startswith("dataset/") and rel.lower().endswith(".md"):
        manifest = read_manifest(db_alias)
        files: list[str] = list(manifest.get("knowledge_files") or [])
        entry = rel
        if entry not in files:
            files.append(entry)
        touch_manifest(db_alias, knowledge_files=files)
    _sync_frontend_project_meta(db_alias, rel)
    _sync_backend_project_meta(db_alias, rel)
    return {
        "path": rel,
        "size": path.stat().st_size,
        "created": True,
    }


def delete_artifact(db_alias: str, rel_path: str) -> dict[str, Any]:
    rel = _normalize_rel_path(rel_path)
    path = resolve_artifact_file(db_alias, rel)
    if not path.exists():
        raise FileNotFoundError(f"不存在: {rel_path}")
    is_dir = path.is_dir()
    root_name = _artifact_root_name(rel)
    if is_dir:
        if root_name == "dataset":
            touch_manifest(db_alias, knowledge_files=[])
        elif rel.startswith("dataset/"):
            _remove_dataset_md_manifests_under(db_alias, path)
        shutil.rmtree(path)
        if root_name:
            _after_artifact_root_delete(db_alias, root_name)
        else:
            _after_frontend_delete(db_alias, rel)
            _after_backend_delete(db_alias, rel)
    else:
        path.unlink()
        _remove_dataset_knowledge_manifest(db_alias, rel)
        _sync_frontend_project_meta(db_alias, rel)
        _sync_backend_project_meta(db_alias, rel)
    return {"path": rel, "deleted": True, "is_dir": is_dir}


def write_artifact(db_alias: str, rel_path: str, content: str) -> dict[str, Any]:
    path = resolve_artifact_file(db_alias, rel_path)
    if path.is_dir():
        raise ValueError("不能写入目录")
    if not _is_text_file(path) and path.exists():
        raise ValueError("该文件类型不支持在线编辑")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"内容过大（>{MAX_FILE_BYTES // 1024 // 1024}MB）")
    rel = rel_path.replace("\\", "/")
    content = enforce_dataset_frontmatter_db_alias(db_alias, rel, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if rel.startswith("dataset/"):
        touch_manifest(db_alias)
    _sync_frontend_project_meta(db_alias, rel)
    _sync_backend_project_meta(db_alias, rel)
    return {
        "path": rel,
        "size": path.stat().st_size,
        "saved": True,
    }
