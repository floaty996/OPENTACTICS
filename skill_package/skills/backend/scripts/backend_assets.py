from __future__ import annotations

import json
from pathlib import Path

from skill_package.core.registry import register_skill_tool
from skill_package.skills.backend.paths import API_MANIFEST_NAME
from skill_package.workspace.file_patch import patch_text_file
from skill_package.workspace.paths import (
    backend_dir,
    list_workspace_aliases,
    read_manifest,
    touch_manifest,
    validate_db_alias,
)

list_schema = {
    "type": "function",
    "function": {
        "name": "list_backend_projects",
        "description": "列举 workspace 下 backend/ 中的后端 API 工程（可按 db_alias 过滤）",
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
        "name": "check_db_connected_backend",
        "description": (
            "检查 workspace/{db_alias}/backend/ 是否已有接库后端工程；"
            "返回 deliverables 清单（是否缺 main.py 等）。全栈收尾前建议配合 verify_fullstack_deliverables。"
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
        "name": "read_backend_file",
        "description": "读取 workspace/{db_alias}/backend/{project_name}/ 内文件",
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string", "description": "工程目录名，如 ethnic-analysis-api"},
                "file_path": {"type": "string", "description": "工程内路径，如 main.py 或 routers/employees.py"},
            },
            "required": ["db_alias", "project_name", "file_path"],
        },
    },
}

save_schema = {
    "type": "function",
    "function": {
        "name": "save_backend_file",
        "description": (
            "整文件写入 workspace/{db_alias}/backend/{project_name}/。"
            "新建文件或大范围重写时用；小范围修改请优先 patch_backend_file。"
            "须含完整 content。新建接库后端须先写 api_manifest.json。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "工作区别名"},
                "project_name": {"type": "string", "description": "backend 下工程目录名"},
                "file_path": {"type": "string", "description": "工程内相对路径"},
                "content": {"type": "string", "description": "要写入的完整文件内容"},
            },
            "required": ["db_alias", "project_name", "file_path", "content"],
        },
    },
}

patch_schema = {
    "type": "function",
    "function": {
        "name": "patch_backend_file",
        "description": (
            "按片段替换 backend 工程内已有文件（old_string → new_string），"
            "比 save_backend_file 更快、省 token。修改前须 read_backend_file 复制精确原文。"
            "多处相同文本时设 occurrence 或 replace_all。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "project_name": {"type": "string"},
                "file_path": {"type": "string"},
                "old_string": {
                    "type": "string",
                    "description": "要被替换的原文片段，须与文件内容完全一致",
                },
                "new_string": {"type": "string", "description": "替换后的内容"},
                "replace_all": {
                    "type": "boolean",
                    "description": "为 true 时替换所有匹配；默认 false 且仅允许唯一匹配",
                },
                "occurrence": {
                    "type": "integer",
                    "description": "replace_all=false 且有多处匹配时，替换第几处（从 1 开始）",
                },
            },
            "required": ["db_alias", "project_name", "file_path", "old_string", "new_string"],
        },
    },
}

run_info_schema = {
    "type": "function",
    "function": {
        "name": "get_backend_run_info",
        "description": (
            "查询后端工程的本地运行方式、默认端口、API 前缀及关联前端工程名；"
            "返回 studio_run_command / studio_gaps / ready_for_studio，供 Skill Studio 系统预览自检。"
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


def _project_root(db_alias: str, project_name: str) -> Path:
    alias = validate_db_alias(db_alias)
    name = project_name.strip().strip("/")
    if not name or ".." in Path(name).parts:
        raise ValueError("project_name 非法")
    root = (backend_dir(alias) / name).resolve()
    root.relative_to(backend_dir(alias).resolve())
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
    mp = proj_dir / API_MANIFEST_NAME
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
        root = backend_dir(alias)
        if not root.is_dir():
            continue
        for manifest_path in root.rglob(API_MANIFEST_NAME):
            if manifest_path.name.startswith("_template"):
                continue
            proj_dir = manifest_path.parent
            project_name = proj_dir.relative_to(root).as_posix()
            meta = _read_manifest_file(proj_dir) or {}
            rows.append(
                {
                    "db_alias": alias,
                    "project_name": project_name,
                    "workspace_path": f"workspace/{alias}/backend/{project_name}",
                    "has_database_connection": bool(meta.get("has_database_connection")),
                    "stack": meta.get("stack"),
                    "linked_frontend": meta.get("linked_frontend"),
                    "default_port": meta.get("default_port"),
                    "api_prefix": meta.get("api_prefix"),
                }
            )
    return sorted(rows, key=lambda r: (r["db_alias"], r["project_name"]))


def _prepare_backend_content(
    rel_path: str, content: str, *, api_prefix: str = "/api"
) -> tuple[str, list[str], list[str]]:
    """自动修正可修复项后，返回仍违反规范的错误（非空则禁止写盘）。"""
    from skill_package.core.fullstack_contract import (
        ensure_main_py_health_snippet,
        fix_relative_imports,
    )
    from skill_package.core.fullstack_enforce import blocking_errors_for_backend_file

    rel = rel_path.strip().lstrip("/")
    body = content
    autofix: list[str] = []
    if rel.endswith(".py"):
        body, ch = fix_relative_imports(body)
        autofix.extend(ch)
        if rel == "main.py":
            body, ch2 = ensure_main_py_health_snippet(body, api_prefix)
            autofix.extend(ch2)
    errors = blocking_errors_for_backend_file(rel, body)
    return body, autofix, errors


def _blocked_payload(violations: list[str], *, file_path: str) -> str:
    from skill_package.core.fullstack_enforce import spec_summary_text

    return json.dumps(
        {
            "ok": False,
            "blocked": True,
            "file_path": file_path,
            "violations": violations,
            "spec_summary": spec_summary_text(),
            "message": "违反全栈生成硬性规范，已拒绝写入。请按 violations 修正 content 后重试 save_backend_file。",
        },
        ensure_ascii=False,
    )


def _after_backend_file_write(
    db_alias: str, project_name: str, file_path: str, target: Path, content: str | None = None
) -> dict:
    """保存或 patch 后同步 manifest、修正常见启动/对接问题。"""
    alias = validate_db_alias(db_alias)
    proj = _project_root(alias, project_name)
    extra: dict = {}
    rel = file_path.strip().lstrip("/")
    meta = _read_manifest_file(proj) or {}
    api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")

    if rel.endswith(".py"):
        from skill_package.core.fullstack_contract import (
            ensure_main_py_health_snippet,
            fix_relative_imports,
        )

        try:
            body = content if content is not None else target.read_text(encoding="utf-8")
        except OSError:
            body = ""
        # 写盘前已在 save/patch 中规范化；此处仅记录
        if body and content is not None:
            extra["content_normalized"] = True

    if file_path.strip().endswith(API_MANIFEST_NAME) or (proj / API_MANIFEST_NAME).exists():
        meta = _read_manifest_file(proj)
        _sync_backend_manifest(alias, project_name, meta)
    if meta:
        port = meta.get("default_port", 8000)
        prefix = meta.get("api_prefix", "/api")
        extra["api_base_url"] = f"http://127.0.0.1:{port}{prefix}"
        if meta.get("linked_frontend"):
            extra["linked_frontend"] = meta["linked_frontend"]
        extra["frontend_next_step"] = (
            f"请 UI_build 调用 get_fullstack_api_contract(db_alias, frontend_project="
            f"{meta.get('linked_frontend')!r}) 后再写 preview.html"
            if meta.get("linked_frontend")
            else "请在 api_manifest.json 设置 linked_frontend 后由 UI_build 对接前端"
        )
    return extra


def _sync_backend_manifest(db_alias: str, project_name: str, meta: dict | None) -> None:
    proj_dir = _project_root(db_alias, project_name)
    manifest = read_manifest(db_alias)
    projects: list[dict] = list(manifest.get("backend_projects") or [])
    m = meta or {}
    entry = {
        "name": project_name,
        "path": f"backend/{project_name}",
        "has_database_connection": bool(m.get("has_database_connection")),
        "has_api_knowledge": (proj_dir / "api_knowledge.md").is_file(),
        "stack": m.get("stack"),
        "linked_frontend": m.get("linked_frontend"),
        "default_port": m.get("default_port"),
        "api_prefix": m.get("api_prefix"),
    }
    projects = [p for p in projects if p.get("name") != project_name]
    projects.append(entry)
    touch_manifest(db_alias, backend_projects=projects)


@register_skill_tool("backend", name="list_backend_projects", schema=list_schema)
def list_backend_projects(db_alias: str | None = None) -> str:
    projects = _scan_projects(db_alias)
    return json.dumps({"ok": True, "projects": projects, "count": len(projects)}, ensure_ascii=False)


@register_skill_tool("backend", name="check_db_connected_backend", schema=check_schema)
def check_db_connected_backend(db_alias: str) -> str:
    from skill_package.core.deliverables import audit_backend_project

    alias = validate_db_alias(db_alias)
    for row in _scan_projects(alias):
        if row.get("has_database_connection"):
            proj_dir = backend_dir(alias) / row["project_name"]
            meta = _read_manifest_file(proj_dir)
            deliverables = audit_backend_project(proj_dir)
            msg = "已存在接库后端，请在其上迭代。"
            if deliverables["missing_required"]:
                msg += (
                    f" 警告：缺少必需文件 {deliverables['missing_required']}，"
                    "须 save_backend_file 补全后才能 uvicorn 启动。"
                )
            if deliverables.get("linked_frontend") and not deliverables.get(
                "linked_frontend_exists"
            ):
                msg += (
                    f" 警告：linked_frontend={deliverables['linked_frontend']!r} 的前端目录不存在，"
                    "须由 UI_build 创建，禁止在回复中声称前端已完成。"
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
            "workspace_backend": f"workspace/{alias}/backend/",
            "message": "未找到接库后端，请在 backend/ 下新建工程并写入 api_manifest.json。",
        },
        ensure_ascii=False,
    )


@register_skill_tool("backend", name="read_backend_file", schema=read_schema)
def read_backend_file(db_alias: str, project_name: str, file_path: str) -> str:
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


@register_skill_tool("backend", name="save_backend_file", schema=save_schema)
def save_backend_file(db_alias: str, project_name: str, file_path: str, content: str) -> str:
    try:
        alias = validate_db_alias(db_alias)
        from skill_package.workspace.paths import ensure_workspace

        ensure_workspace(alias)
        target = _resolve_file(alias, project_name, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rel = file_path.strip().lstrip("/")
        proj = _project_root(alias, project_name)
        meta = _read_manifest_file(proj) or {}
        api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        body, autofix, violations = _prepare_backend_content(rel, content, api_prefix=api_prefix)
        if violations:
            return _blocked_payload(violations, file_path=rel)
        target.write_text(body, encoding="utf-8")
        extra = _after_backend_file_write(alias, project_name, file_path, target, body)
        if autofix:
            extra["auto_fixed"] = autofix
        payload: dict = {
            "ok": True,
            "db_alias": alias,
            "project_name": project_name,
            "path": str(target),
            "workspace_path": f"workspace/{alias}/backend/{project_name}/{file_path.lstrip('/')}",
            "bytes": target.stat().st_size,
            "mode": "full_write",
            **extra,
        }
        proj = _project_root(alias, project_name)
        meta = _read_manifest_file(proj)
        if meta:
            port = meta.get("default_port", 8000)
            payload["run_hint"] = (
                f"本地运行示例：cd workspace/{alias}/backend/{project_name} && "
                f"pip install -r requirements.txt && "
                f"uvicorn main:app --reload --port {port}"
            )
        return json.dumps(payload, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="patch_backend_file", schema=patch_schema)
def patch_backend_file(
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
        rel = file_path.strip().lstrip("/")
        patched_body = target.read_text(encoding="utf-8")
        meta = _read_manifest_file(_project_root(alias, project_name)) or {}
        api_prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        autofix: list[str] = []
        if rel in (API_MANIFEST_NAME, "requirements.txt") or rel.endswith(".py"):
            body, autofix, violations = _prepare_backend_content(
                rel,
                patched_body,
                api_prefix=api_prefix,
            )
            if violations:
                return _blocked_payload(violations, file_path=rel)
            if body != patched_body:
                target.write_text(body, encoding="utf-8")
            patched_body = body
        extra = _after_backend_file_write(
            alias, project_name, file_path, target, patched_body if rel.endswith(".py") else None
        )
        if autofix:
            extra["auto_fixed"] = autofix
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "path": str(target),
                "workspace_path": f"workspace/{alias}/backend/{project_name}/{file_path.lstrip('/')}",
                "mode": "patch",
                **patch_meta,
                **extra,
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="get_backend_run_info", schema=run_info_schema)
def get_backend_run_info(db_alias: str, project_name: str) -> str:
    try:
        from skill_package.core.deliverables import audit_backend_project

        alias = validate_db_alias(db_alias)
        proj = _project_root(alias, project_name)
        if not proj.is_dir():
            return json.dumps(
                {"ok": False, "error": f"工程不存在: backend/{project_name}/"},
                ensure_ascii=False,
            )
        meta = _read_manifest_file(proj) or {}
        port = int(meta.get("default_port") or 8000)
        prefix = str(meta.get("api_prefix") if meta.get("api_prefix") is not None else "/api")
        if prefix and (not prefix.startswith("/") or "（" in prefix or "）" in prefix):
            prefix = "/api"
        prefix = prefix.rstrip("/") or ""
        stack = meta.get("stack") or "fastapi"
        linked = meta.get("linked_frontend") or ""
        audit = audit_backend_project(proj)
        studio_cmd = f"uvicorn main:app --host 127.0.0.1 --port {port}"
        return json.dumps(
            {
                "ok": True,
                "db_alias": alias,
                "project_name": project_name,
                "stack": stack,
                "default_port": port,
                "api_prefix": prefix or "/api",
                "api_base_url": f"http://127.0.0.1:{port}{prefix}",
                "linked_frontend": linked,
                "workspace_path": f"workspace/{alias}/backend/{project_name}/",
                "ready_for_studio": audit.get("ready_for_studio", False),
                "studio_gaps": audit.get("studio_gaps") or [],
                "run_commands": [
                    f"cd skill_package/workspace/{alias}/backend/{project_name}",
                    "pip install -r requirements.txt",
                    f"uvicorn main:app --reload --host 127.0.0.1 --port {port}",
                ],
                "studio_run_command": studio_cmd,
                "studio_env_vars": [
                    "STUDIO_WORKSPACE_CONFIG",
                    "STUDIO_DB_ALIAS",
                    "STUDIO_STORAGE_MODE",
                    "STUDIO_LOCAL_SQLITE",
                    "DB_PASSWORD",
                    "DB_TARGET_PASSWORD",
                ],
                "studio_notes": (
                    "Skill Studio 系统预览由 backend_runner 执行 studio_run_command（无 --reload），"
                    "并注入 studio_env_vars；main.py 须可 import，api_manifest.api_prefix 只能是 /api 或空字符串。"
                ),
                "frontend_integration_hint": (
                    f"前端 preview.html 或 Vite 开发服请将 API 指向 http://127.0.0.1:{port}{prefix}；"
                    f"建议在 api_knowledge.md 与 frontend 的 ui_knowledge.md 中写明接口路径。"
                ),
            },
            ensure_ascii=False,
        )
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


verify_fullstack_schema = {
    "type": "function",
    "function": {
        "name": "verify_fullstack_deliverables",
        "description": (
            "只读检查当前 saas 工作区全栈交付物是否齐全（backend + frontend + 关键文件）。"
            "向用户声称「系统/全栈已完成」之前必须调用；system_complete 为 false 时按 gaps 继续写盘。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"db_alias": {"type": "string"}},
            "required": ["db_alias"],
        },
    },
}

fullstack_contract_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_api_contract",
        "description": (
            "返回前后端 API 对接契约（路由表、api_base_url、preview_api_block）。"
            "backend 写完 main.py 后、UI_build 写 preview.html 之前应调用，确保 linked_frontend 正确。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {"type": "string"},
                "backend_project": {"type": "string"},
            },
            "required": ["db_alias"],
        },
    },
}


scaffold_schema = {
    "type": "function",
    "function": {
        "name": "scaffold_fullstack_project",
        "description": (
            "【新建全栈系统首选】按硬性规范一次性生成 backend + frontend 可启动骨架"
            "（api_manifest、main.py、requirements、preview.html、知识文档）。"
            "生成后再 save_backend_file 补充 routers 业务逻辑。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string"},
                "frontend_project": {"type": "string", "description": "前端目录名，如 my-app-web"},
                "backend_project": {"type": "string", "description": "可选，默认 {frontend}-api"},
                "service_title": {"type": "string", "description": "服务/页面标题"},
                "write_to_disk": {
                    "type": "boolean",
                    "description": "为 true 时直接落盘；默认 true",
                },
            },
            "required": ["db_alias", "frontend_project"],
        },
    },
}

spec_schema = {
    "type": "function",
    "function": {
        "name": "get_fullstack_generation_spec",
        "description": "返回全栈生成的硬性规范（流程、禁止项、收尾门禁），新建系统前应先阅读。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


@register_skill_tool("backend", name="get_fullstack_generation_spec", schema=spec_schema)
def get_fullstack_generation_spec() -> str:
    from skill_package.core.fullstack_enforce import GENERATION_SPEC, spec_summary_text

    return json.dumps(
        {
            "ok": True,
            "summary": spec_summary_text(),
            "spec": GENERATION_SPEC,
        },
        ensure_ascii=False,
    )


@register_skill_tool("backend", name="scaffold_fullstack_project", schema=scaffold_schema)
def scaffold_fullstack_project(
    db_alias: str,
    frontend_project: str,
    backend_project: str | None = None,
    service_title: str = "业务系统",
    write_to_disk: bool = True,
) -> str:
    from skill_package.core.fullstack_scaffold import build_scaffold_plan, write_scaffold_to_workspace
    from skill_package.workspace.paths import ensure_workspace

    try:
        alias = validate_db_alias(db_alias)
        ensure_workspace(alias)
        plan = build_scaffold_plan(
            alias,
            frontend_project=frontend_project,
            backend_project=backend_project,
            service_title=service_title or "业务系统",
        )
        if write_to_disk:
            written = write_scaffold_to_workspace(plan)
            plan["written"] = written["written"]
            plan["message"] = (
                f"已按规范生成并落盘 backend/{plan['backend_project']} 与 "
                f"frontend/{plan['frontend_project']}，请继续补充 routers 与页面业务逻辑。"
            )
        else:
            plan["message"] = "已生成脚手架计划（未写盘），请对各文件调用 save_*_file。"
        return json.dumps(plan, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@register_skill_tool("backend", name="get_fullstack_api_contract", schema=fullstack_contract_schema)
def get_fullstack_api_contract_backend(
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


@register_skill_tool("backend", name="verify_fullstack_deliverables", schema=verify_fullstack_schema)
def verify_fullstack_deliverables(db_alias: str) -> str:
    from skill_package.core.deliverables import verify_fullstack_status

    try:
        return json.dumps(verify_fullstack_status(db_alias), ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
