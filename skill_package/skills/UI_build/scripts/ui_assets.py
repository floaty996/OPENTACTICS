from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.UI_build.paths import UI_MANIFEST_NAME
from skill_package.workspace.file_patch import patch_text_file
from skill_package.workspace.paths import (
    backend_dir,
    frontend_dir,
    list_workspace_aliases,
    read_manifest,
    touch_manifest,
    validate_db_alias,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_ui_assets",
        "description": "列举 workspace 下 frontend/ 中的前端工程（可按 db_alias 过滤）",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "省略则列举全部工作区"},
            },
            "required": [],
        },
    },
}

check_schema = {
    "type": "function",
    "function": {
        "name": "check_db_connected_frontend",
        "description": (
            "检查 workspace/{db_alias}/frontend/ 是否已有接库前端工程；"
            "返回 deliverables（是否缺 preview.html 等）。全栈收尾前建议 verify_fullstack_deliverables。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}

read_schema = {
    "type": "function",
    "function": {
        "name": "read_ui_asset",
        "description": "读取 workspace/{db_alias}/frontend/{project_name}/ 内文件",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string", "description": "工程目录名，如 admin-web"},
                "file_path": {"type": "string", "description": "工程内路径，如 src/App.tsx"},
            },
            "required": ["db_alias", "project_name", "file_path"],
        },
    },
}

save_schema = {
    "type": "function",
    "function": {
        "name": "save_ui_file",
        "description": (
            "整文件写入 frontend 工程；新建或大改时用。"
            "小范围改 HTML/JS/CSS 请优先 patch_ui_file。"
            "须含完整 content。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "工作区别名，与当前 saas 一致"},
                "project_name": {"type": "string", "description": "frontend 下工程目录名"},
                "file_path": {"type": "string", "description": "工程内相对路径，如 preview.html"},
                "content": {"type": "string", "description": "要写入的完整文件内容"},
            },
            "required": ["db_alias", "project_name", "file_path", "content"],
        },
    },
}

patch_schema = {
    "type": "function",
    "function": {
        "name": "patch_ui_file",
        "description": (
            "按片段替换 frontend 工程内已有文件（old_string → new_string）。"
            "修改前须 read_ui_asset 复制精确原文。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
                "occurrence": {"type": "integer"},
            },
            "required": ["db_alias", "project_name", "file_path", "old_string", "new_string"],
        },
    },
}


def _project_root(db_alias: str, project_name: str) -> Path:
    alias = validate_db_alias(db_alias)
    name = project_name.strip().strip("/")
    if not name or ".." in Path(name).parts:
        raise ValueError("project_name 非法")
    root = (frontend_dir(alias) / name).resolve()
    root.relative_to(frontend_dir(alias).resolve())
    return root


def _resolve_file(db_alias: str, project_name: str, file_path: str) -> Path:
    proj = _project_root(db_alias, project_name)
    rel = file_path.strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise ValueError("file_path 非法")
    target = (proj / rel).resolve()
    target.relative_to(proj)
    return target


def _read_manifest_file(proj_dir: Path) -> dict | None:
    mp = proj_dir / UI_MANIFEST_NAME
    if not mp.is_file():
        return None
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _scan_projects(db_alias: str | None = None) -> list[dict]:
    aliases = [validate_db_alias(db_alias)] if db_alias and db_alias.strip() else list_workspace_aliases()
    rows: list[dict] = []
    for alias in aliases:
        root = frontend_dir(alias)
        if not root.is_dir():
            continue
        for manifest_path in root.rglob(UI_MANIFEST_NAME):
            if manifest_path.name.startswith("_template"):
                continue
            proj_dir = manifest_path.parent
            project_name = proj_dir.relative_to(root).as_posix()
            meta = _read_manifest_file(proj_dir) or {}
            rows.append(
                {
                    "db_alias": alias,
                    "project_name": project_name,
                    "workspace_path": f"workspace/{alias}/frontend/{project_name}",
                    "has_database_connection": bool(meta.get("has_database_connection")),
                    "stack": meta.get("stack"),
                }
            )
    return sorted(rows, key=lambda r: (r["db_alias"], r["project_name"]))


def find_preview_entry(proj_dir: Path) -> str | None:
    """返回工程内可用于 Studio 静态预览的 HTML 相对路径。"""
    for rel in ("preview.html", "index.html", "dist/index.html", "public/index.html"):
        if (proj_dir / rel).is_file():
            return rel
    return None


def _after_ui_file_write(db_alias: str, project_name: str, file_path: str, target: Path) -> dict:
    alias = validate_db_alias(db_alias)
    proj = _project_root(alias, project_name)
    if file_path.strip().endswith(UI_MANIFEST_NAME) or (proj / UI_MANIFEST_NAME).exists():
        meta = _read_manifest_file(proj)
        _sync_project_manifest(alias, project_name, meta)
    elif file_path.strip().endswith((".html", ".htm")):
        _sync_project_manifest(alias, project_name, _read_manifest_file(proj))
    extra: dict = {}
    preview = find_preview_entry(proj)
    if preview:
        extra["preview_entry"] = preview
        extra["studio_preview_hint"] = (
            f"用户可在 Skill Studio「系统预览」中查看，路径 frontend/{project_name}/{preview}"
        )
    if file_path.strip().endswith((".html", ".htm")):
        from skill_package.core.deliverables import audit_frontend_project
        from skill_package.core.fullstack_contract import (
            build_api_contract,
            ensure_preview_api_block,
        )
        from skill_package.skills.backend.scripts.backend_assets import (
            _read_manifest_file as read_be_manifest,
            _scan_projects as scan_be,
        )

        linked_meta = None
        for row in scan_be(alias):
            if row.get("linked_frontend") == project_name:
                be_dir = backend_dir(alias) / row["project_name"]
                linked_meta = read_be_manifest(be_dir)
                break
        try:
            contract = build_api_contract(alias, frontend_project=project_name)
            raw = target.read_text(encoding="utf-8")
            merged, inject_changes = ensure_preview_api_block(raw, contract)
            if merged != raw:
                target.write_text(merged, encoding="utf-8")
                extra["fullstack_api_injected"] = inject_changes
            extra["api_contract"] = {
                "api_base_url": contract.get("api_base_url"),
                "backend_routes": contract.get("backend_routes"),
                "fetch_path_rule": contract.get("fetch_path_rule"),
            }
            if contract.get("gaps"):
                extra["contract_gaps"] = contract["gaps"]
            audit = audit_frontend_project(proj, linked_backend_meta=linked_meta)
            if audit.get("studio_gaps"):
                extra["studio_gaps"] = audit["studio_gaps"]
                extra["must_fix_before_complete"] = (
                    "preview.html 仍未通过全栈契约检查，禁止向用户声称前后端已联动："
                    + "；".join(audit["studio_gaps"])
                )
        except ValueError as e:
            extra["api_contract_warning"] = str(e)
            extra["must_call"] = (
                "后端尚未就绪或 linked_frontend 未配置；请先 backend skill 完成 API，"
                "再 get_fullstack_api_contract 后重写 preview.html"
            )
        except OSError:
            pass
    return extra


def _sync_project_manifest(db_alias: str, project_name: str, meta: dict | None) -> None:
    proj_dir = _project_root(db_alias, project_name)
    manifest = read_manifest(db_alias)
    projects: list[dict] = list(manifest.get("projects") or [])
    entry = {
        "name": project_name,
        "path": f"frontend/{project_name}",
        "has_database_connection": bool((meta or {}).get("has_database_connection")),
        "has_ui_knowledge": (proj_dir / "ui_knowledge.md").is_file(),
        "preview_entry": find_preview_entry(proj_dir),
    }
    projects = [p for p in projects if p.get("name") != project_name]
    projects.append(entry)
    touch_manifest(db_alias, projects=projects)


preview_schema = {
    "type": "function",
    "function": {
        "name": "get_frontend_preview",
        "description": (
            "获取前端工程在 Skill Studio 中的静态预览入口（HTML 路径）。"
            "新建工程时请提供 preview.html 或 index.html 以便用户预览整页效果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
            },
            "required": ["db_alias", "project_name"],
        },
    },
}

contract_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_api_contract",
        "description": (
            "【写 preview.html 之前必调】返回前后端 API 对接契约：api_base_url、backend_routes、"
            "preview_api_block（标准 fetch 层）。save_ui_file 会自动注入该块，但 agent 须按 "
            "backend_routes 编写业务 fetch，且禁止自写 const API / 硬编码端口。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {
                    "type": "string",
                    "description": "前端工程名；与 backend linked_frontend 对应",
                },
                "backend_project": {
                    "type": "string",
                    "description": "可选；省略时按 linked_frontend 自动关联",
                },
            },
            "required": ["db_alias"],
        },
    },
}


@register_skill_tool("UI_build", name="list_ui_assets", schema=list_schema)
def list_ui_assets(db_alias: str | None = None) -> str:
    projects = _scan_projects(db_alias)
    return json.dumps({"ok": True, "projects": projects, "count": len(projects)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="check_db_connected_frontend", schema=check_schema)
def check_db_connected_frontend(db_alias: str) -> str:
    from skill_package.core.deliverables import audit_frontend_project

    alias = validate_db_alias(db_alias)
    for row in _scan_projects(alias):
        if row.get("has_database_connection"):
            proj_dir = frontend_dir(alias) / row["project_name"]
            meta = _read_manifest_file(proj_dir)
            deliverables = audit_frontend_project(proj_dir)
            msg = "已存在接库前端，请在其上迭代。"
            if deliverables["missing_required"]:
                msg += (
                    f" 警告：缺少 {deliverables['missing_required']}，"
                    "须 save_ui_file 写入 preview.html 等后方可 Studio 预览。"
                )
            return json.dumps(
                {
                    "ok": True,
                    "exists": True,
                    "db_alias": alias,
                    "project_name": row["project_name"],
                    "workspace_path": row["workspace_path"],
                    "manifest": meta,
                    "deliverables": deliverables,
                    "message": msg,
                },
                ensure_ascii=False,
            )
    return json.dumps(
        {
            "ok": True,
            "exists": False,
            "db_alias": alias,
            "workspace_frontend": f"workspace/{alias}/frontend/",
            "message": (
                "未找到接库前端，须在 frontend/ 下新建工程、ui_manifest.json，"
                "并用 save_ui_file 写入 preview.html；禁止仅用文字描述前端已完成。"
            ),
        },
        ensure_ascii=False,
    )


@register_skill_tool("UI_build", name="read_ui_asset", schema=read_schema)
def read_ui_asset(db_alias: str, project_name: str, file_path: str) -> str:
    try:
        target = _resolve_file(db_alias, project_name, file_path)
        if not target.exists():
            return json.dumps({"ok": False, "error": f"文件不存在: {target}"}, ensure_ascii=False)
        content = target.read_text(encoding="utf-8")
        if len(content) > 80000:
            content = content[:80000] + "\n...[TRUNCATED]"
        return json.dumps(
            {
                "ok": True,
                "db_alias": validate_db_alias(db_alias),
                "project_name": project_name,
                "file_path": file_path,
                "content": content,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="save_ui_file", schema=save_schema)
def save_ui_file(db_alias: str, project_name: str, file_path: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        rel = file_path.strip().lstrip("/")
        if rel.endswith((".html", ".htm")):
            from skill_package.core.fullstack_enforce import validate_preview_html, spec_summary_text

            violations = validate_preview_html(content)
            if violations:
                return json.dumps(
                    {
                        "ok": False,
                        "blocked": True,
                        "violations": violations,
                        "spec_summary": spec_summary_text(),
                        "message": "违反全栈前端规范，已拒绝写入 preview。请移除 const API / 硬编码端口后重试。",
                    },
                    ensure_ascii=False,
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        extra = _after_ui_file_write(alias, project_name, file_path, target)
        payload: dict = {
            "ok": True,
            "db_alias": alias,
            "project_name": project_name,
            "path": str(target),
            "workspace_path": f"workspace/{alias}/frontend/{project_name}/{file_path.lstrip('/')}",
            "bytes": target.stat().st_size,
            "mode": "full_write",
            **extra,
        }
        if extra.get("studio_gaps"):
            payload["ok"] = False
            payload["blocked"] = True
            payload["violations"] = extra["studio_gaps"]
            payload["message"] = extra.get("must_fix_before_complete") or "preview 未通过全栈契约检查"
        return json.dumps(payload, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="patch_ui_file", schema=patch_schema)
def patch_ui_file(
    db_alias: str,
    project_name: str,
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    occurrence: int = 1,
) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        patch_meta = patch_text_file(
            target,
            old_string,
            new_string,
            replace_all=bool(replace_all),
            occurrence=int(occurrence or 1),
        )
        extra = _after_ui_file_write(alias, project_name, file_path, target)
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{file_path.lstrip('/')}",
                "mode": "patch",
                **patch_meta,
                **extra,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="get_fullstack_api_contract", schema=contract_schema)
def get_fullstack_api_contract_ui(
    db_alias: str,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> str:
    from skill_package.core.fullstack_contract import build_api_contract

    try:
        return json.dumps(
            build_api_contract(
                db_alias,
                frontend_project=frontend_project,
                backend_project=backend_project,
            ),
            ensure_ascii=False,
        )
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("UI_build", name="get_frontend_preview", schema=preview_schema)
def get_frontend_preview(db_alias: str, project_name: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir():
            return json.dumps(
                {"ok": False, "error": f"工程不存在: frontend/{project_name}/"},
                ensure_ascii=False,
            )
        entry = find_preview_entry(proj)
        if not entry:
            return json.dumps(
                {
                    "ok": True,
                    "has_preview": False,
                    "db_alias": alias,
                    "project_name": project_name,
                    "message": "未找到 preview.html / index.html，请创建 standalone 的 preview.html 供 Studio 预览。",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "has_preview": True,
                "db_alias": alias,
                "project_name": project_name,
                "preview_entry": entry,
                "workspace_path": f"workspace/{alias}/frontend/{project_name}/{entry}",
                "studio_preview_hint": "用户在 Skill Studio 产物页可切换「预览」查看整页效果。",
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
