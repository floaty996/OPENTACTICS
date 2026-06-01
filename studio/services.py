"""配置落盘与 skill 对话服务。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agents.deepseek_backend import DEFAULT_CONFIG_PATH, load_deepseek_config
from agents.llm_config import normalize_llm_provider, workspace_llm_status
from skill_package import SkillCaller, get_tool_function
from skill_package.core.registry import get_tool_display_labels, get_tool_schemas_for_skills
from skill_package.skills.database.mysql_errors import format_db_connection_error
from skill_package.workspace.config_loader import (
    load_workspace_config,
    load_workspace_db_config,
    mask_config_secrets,
    merge_preserved_secrets,
    is_redacted_secret,
)
from skill_package.workspace import conversations_store as conv_store
from skill_package.core.fullstack_orchestration import build_fullstack_orchestration_note
from skill_package.workspace.local_store import DEFAULT_LOCAL_SQLITE_REL, ensure_local_sqlite
from skill_package.workspace.paths import config_path, ensure_workspace, touch_manifest, validate_db_alias
from skill_package.custom_skills_store import (
    delete_custom_skill as _delete_custom_skill_dir,
    extract_custom_skill_zip,
    import_custom_skill_files,
    iter_custom_skill_dirs,
    list_custom_skill_ids,
    validate_skill_id,
)
from skill_package.core.skill import Skill
from skill_package.skill_author_uploads import (
    build_upload_context,
    list_uploads as list_skill_author_uploads,
    new_session_id,
    save_upload as save_skill_author_upload,
    validate_session_id,
)
from skill_package.workspace.source_files_store import (
    delete_source_file as _delete_source_file,
    list_source_files,
    upload_source_files,
)

_ROOT = Path(__file__).resolve().parents[1]
STUDIO_STATE_PATH = _ROOT / "config" / "studio_state.json"

skill_caller = SkillCaller(execute_blocks=True)

_skill_author_session: str | None = None


_WORKSPACE_ALIAS_TOOLS = frozenset(
    {
        "save_ui_file",
        "patch_ui_file",
        "read_ui_asset",
        "save_ui_knowledge",
        "read_ui_knowledge",
        "get_frontend_preview",
        "get_fullstack_api_contract",
        "get_fullstack_generation_spec",
        "scaffold_fullstack_project",
        "check_db_connected_frontend",
        "list_ui_assets",
        "list_backend_projects",
        "check_db_connected_backend",
        "verify_fullstack_deliverables",
        "read_backend_file",
        "save_backend_file",
        "patch_backend_file",
        "read_api_knowledge",
        "save_api_knowledge",
        "get_backend_run_info",
        "save_database_config",
        "read_database_config",
        "list_database_configs",
        "read_workspace_manifest",
        "save_markdown",
        "patch_markdown",
        "read_database_knowledge",
        "list_database_knowledge",
        "database_connect",
        "list_source_files",
        "read_source_file",
    }
)


def set_skill_author_session(session_id: str | None) -> None:
    global _skill_author_session
    _skill_author_session = session_id


def _normalize_tool_arguments(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {}
    args = dict(arguments)
    if name in _WORKSPACE_ALIAS_TOOLS and not str(args.get("db_alias", "")).strip():
        alias = load_studio_state().get("db_alias", "")
        if alias:
            args["db_alias"] = str(alias)
    if name in ("list_skill_author_uploads", "read_skill_author_upload"):
        if not str(args.get("session_id", "")).strip() and _skill_author_session:
            args["session_id"] = _skill_author_session
    return args


def _run_tool(name: str, arguments: dict[str, Any]) -> str:
    fn = get_tool_function(name)
    if fn is None:
        return json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False)
    args = _normalize_tool_arguments(name, arguments)
    try:
        result = fn(**args)
        if name in ("create_custom_skill", "write_custom_skill_file", "delete_custom_skill"):
            skill_caller.orchestrator.refresh_skills()
        return result
    except TypeError as e:
        err = str(e)
        hint = "请补全工具参数后重试。"
        if "save_ui_file" in name or name == "save_ui_file":
            hint = (
                "save_ui_file 必须传入 db_alias、project_name、file_path、content；"
                "content 为完整文件正文，不可为空。"
            )
        return json.dumps({"ok": False, "error": err, "hint": hint}, ensure_ascii=False)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


def save_deepseek_config(
    *,
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-chat",
    max_tool_rounds: int = 50,
) -> Path:
    path = DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_key": api_key.strip(),
        "base_url": base_url.strip() or "https://api.deepseek.com",
        "model": model.strip() or "deepseek-chat",
        "max_tool_rounds": max_tool_rounds,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _ensure_ui_tools() -> None:
    skill_caller.orchestrator.ensure_tools_loaded("UI_build")


def save_workspace_config(
    *,
    db_alias: str,
    host: str,
    port: int,
    user: str,
    password: str,
    source_databases: list[str],
    target_database: str,
    target_user: str | None = None,
    target_password: str | None = None,
    llm_provider: str = "deepseek",
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
) -> dict[str, Any]:
    """写入 workspace config.json（支持无目标库 → 本地 SQLite）。"""
    alias = validate_db_alias(db_alias)
    ensure_workspace(alias)
    sources = [s.strip() for s in source_databases if s.strip()]
    target = target_database.strip()
    storage_mode = "mysql" if target else "local"
    local_rel = DEFAULT_LOCAL_SQLITE_REL

    if storage_mode == "local":
        ensure_local_sqlite(alias, rel_path=local_rel)

    path = config_path(alias)
    existing: dict[str, Any] | None = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            existing = raw if isinstance(raw, dict) else None
        except (json.JSONDecodeError, OSError):
            existing = None

    payload: dict[str, Any] = {
        "db_alias": alias,
        "db_type": "mysql" if storage_mode == "mysql" else "sqlite",
        "storage_mode": storage_mode,
        "local_sqlite_path": local_rel,
        "host": host.strip(),
        "port": int(port),
        "user": user.strip(),
        "password": password,
        "source_databases": sources,
        "target_database": target,
        "target_user": (target_user or user).strip(),
        "target_password": target_password if target_password is not None else password,
        "file_path": local_rel if storage_mode == "local" else None,
        "llm_provider": normalize_llm_provider(llm_provider),
        "gemini_model": (gemini_model or "").strip() or "gemini-2.0-flash",
    }
    if gemini_api_key is not None and str(gemini_api_key).strip():
        payload["gemini_api_key"] = str(gemini_api_key).strip()
    elif existing and existing.get("gemini_api_key"):
        payload["gemini_api_key"] = existing.get("gemini_api_key")
    payload = merge_preserved_secrets(payload, existing)
    if existing and existing.get("source_files"):
        from skill_package.workspace.source_files_store import normalize_source_files

        payload["source_files"] = normalize_source_files(existing.get("source_files"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    touch_manifest(
        alias,
        has_config=True,
        storage_mode=storage_mode,
        source_databases=sources,
        target_database=target,
        source_files=payload.get("source_files") or [],
    )
    return {
        "ok": True,
        "path": str(path),
        "db_alias": alias,
        "storage_mode": storage_mode,
        "config": mask_config_secrets(payload),
    }


def save_mysql_workspace(
    *,
    db_alias: str,
    host: str,
    port: int,
    user: str,
    password: str,
    source_databases: list[str],
    target_database: str,
    target_user: str | None = None,
    target_password: str | None = None,
) -> dict[str, Any]:
    _ensure_ui_tools()
    alias = validate_db_alias(db_alias)
    ensure_workspace(alias)
    payload = {
        "db_alias": alias,
        "db_type": "mysql",
        "host": host.strip(),
        "port": int(port),
        "user": user.strip(),
        "password": password,
        "source_databases": source_databases,
        "target_database": target_database.strip(),
        "target_user": (target_user or user).strip(),
        "target_password": target_password if target_password is not None else password,
        "file_path": None,
    }
    result = json.loads(_run_tool("save_database_config", payload))
    if not result.get("ok"):
        raise ValueError(result.get("error", "保存数据库配置失败"))
    return result


def test_mysql_connection(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    role: str | None = None,
) -> None:
    try:
        import pymysql
    except ImportError as e:
        raise RuntimeError("未安装 pymysql，请执行: pip install pymysql") from e

    db = database.strip()
    try:
        conn = pymysql.connect(
            host=host.strip(),
            port=int(port),
            user=user.strip(),
            password=password,
            database=db,
            connect_timeout=10,
            read_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as e:
        raise ValueError(
            format_db_connection_error(e, database=db, role=role)
        ) from e


def test_all_databases(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    source_databases: list[str],
    target_database: str,
    target_user: str | None,
    target_password: str | None,
) -> None:
    for db in source_databases:
        test_mysql_connection(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
            role="源库",
        )
    test_mysql_connection(
        host=host,
        port=port,
        user=target_user or user,
        password=target_password if target_password is not None else password,
        database=target_database,
        role="目标库",
    )


def save_studio_state(
    db_alias: str,
    *,
    conversation_id: str | None = None,
    clear_conversation: bool = False,
) -> None:
    STUDIO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prev = load_studio_state()
    alias = validate_db_alias(db_alias)
    payload: dict[str, Any] = {"db_alias": alias}
    if clear_conversation:
        pass
    elif conversation_id is not None:
        payload["conversation_id"] = conversation_id
    elif prev.get("db_alias") == alias and prev.get("conversation_id"):
        payload["conversation_id"] = prev["conversation_id"]
    STUDIO_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _require_db_alias() -> str:
    alias = load_studio_state().get("db_alias", "")
    if not alias:
        raise ValueError("未选择 saas")
    return str(alias)


def list_workspace_artifacts() -> dict[str, Any]:
    from studio.artifacts import list_artifact_tree

    return list_artifact_tree(_require_db_alias())


def get_workspace_artifact(path: str) -> dict[str, Any]:
    from studio.artifacts import read_artifact

    return read_artifact(_require_db_alias(), path)


def save_workspace_artifact(path: str, content: str) -> dict[str, Any]:
    from studio.artifacts import write_artifact

    return write_artifact(_require_db_alias(), path, content)


def create_workspace_artifact(path: str, content: str = "") -> dict[str, Any]:
    from studio.artifacts import create_artifact

    return create_artifact(_require_db_alias(), path, content)


def delete_workspace_artifact(path: str) -> dict[str, Any]:
    from studio.artifacts import delete_artifact

    return delete_artifact(_require_db_alias(), path)


def list_frontend_projects() -> list[dict[str, Any]]:
    from studio.frontend_preview import list_frontend_projects as _list

    return _list(_require_db_alias())


def get_system_preview_summary() -> dict[str, Any]:
    from studio.system_preview import get_system_preview

    return get_system_preview(_require_db_alias())


def start_system_preview_backend(
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    from studio.backend_runner import ensure_backend_running

    return ensure_backend_running(
        _require_db_alias(),
        frontend_project=frontend_project,
        backend_project=backend_project,
    )


def restart_system_preview_backend(
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    from studio.backend_runner import restart_backend_running

    return restart_backend_running(
        _require_db_alias(),
        frontend_project=frontend_project,
        backend_project=backend_project,
    )


def get_system_preview_backend_log(
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
    tail_lines: int = 500,
    reset_watch: bool = False,
) -> dict[str, Any]:
    from studio.backend_runner import read_backend_log

    return read_backend_log(
        _require_db_alias(),
        frontend_project=frontend_project,
        backend_project=backend_project,
        tail_lines=tail_lines,
        reset_watch=reset_watch,
    )


def resolve_frontend_preview_path(project_name: str, file_path: str | None = None) -> Path:
    from studio.frontend_preview import resolve_preview_file

    return resolve_preview_file(_require_db_alias(), project_name, file_path)


def list_conversations() -> list[dict[str, Any]]:
    return conv_store.list_conversations(_require_db_alias())


def get_conversation(conversation_id: str) -> dict[str, Any]:
    return conv_store.load_conversation(_require_db_alias(), conversation_id)


def create_conversation(*, title: str = "新对话") -> dict[str, Any]:
    alias = _require_db_alias()
    ensure_workspace(alias)
    conv = conv_store.create_conversation(alias, title=title)
    save_studio_state(alias, conversation_id=conv["id"])
    return conv


def delete_conversation(conversation_id: str) -> dict[str, Any]:
    alias = _require_db_alias()
    cid = str(conversation_id).strip()
    conv_store.delete_conversation(alias, cid)
    state = load_studio_state()
    was_active = state.get("conversation_id") == cid
    if was_active:
        save_studio_state(alias, clear_conversation=True)
    return {"id": cid, "was_active": was_active}


def persist_conversation_messages(
    conversation_id: str | None,
    messages: list[dict[str, str]],
    *,
    title: str | None = None,
) -> dict[str, Any]:
    alias = _require_db_alias()
    ensure_workspace(alias)
    if conversation_id:
        conv = conv_store.save_conversation_messages(
            alias, conversation_id, messages, title=title
        )
    else:
        conv = conv_store.create_conversation(alias, title=title or "新对话")
        conv = conv_store.save_conversation_messages(alias, conv["id"], messages, title=title)
    save_studio_state(alias, conversation_id=conv["id"])
    return conv


def _normalize_source_databases(raw: dict[str, Any]) -> list[str]:
    sources = raw.get("source_databases") or []
    if isinstance(sources, str):
        sources = [sources]
    return [str(s) for s in sources if str(s).strip()]


def project_setup_form_from_config(alias: str, raw: dict[str, Any]) -> dict[str, Any]:
    """编辑表单所需字段（不含密码明文）。"""
    return {
        "db_alias": alias,
        "host": raw.get("host", ""),
        "port": raw.get("port", 3306),
        "user": raw.get("user", ""),
        "source_databases": _normalize_source_databases(raw),
        "target_database": raw.get("target_database") or raw.get("database") or "",
        "storage_mode": raw.get("storage_mode") or ("mysql" if raw.get("target_database") else "local"),
        "local_sqlite_path": raw.get("local_sqlite_path") or DEFAULT_LOCAL_SQLITE_REL,
        "target_user": raw.get("target_user") or "",
        "has_password": bool(raw.get("password")),
        "has_target_password": bool(raw.get("target_password")),
        "source_files": raw.get("source_files") or [],
        "llm_provider": normalize_llm_provider(raw.get("llm_provider")),
        "gemini_model": raw.get("gemini_model") or "gemini-2.0-flash",
        "has_gemini_api_key": bool(str(raw.get("gemini_api_key") or "").strip())
        and not is_redacted_secret(raw.get("gemini_api_key")),
    }


def list_projects() -> list[dict[str, Any]]:
    """列举 workspace 下已配置的项目（含 config.json）。"""
    from skill_package.workspace.paths import (
        backend_dir,
        dataset_dir,
        frontend_dir,
        list_workspace_aliases,
        read_manifest,
    )

    state = load_studio_state()
    active = state.get("db_alias", "")
    projects: list[dict[str, Any]] = []

    for alias in list_workspace_aliases():
        cfg_file = config_path(alias)
        if not cfg_file.is_file():
            continue
        try:
            raw = json.loads(cfg_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            ds_dir = dataset_dir(alias)
            fe_dir = frontend_dir(alias)
            dataset_count = (
                len([p for p in ds_dir.rglob("*.md") if not p.name.startswith("_")])
                if ds_dir.is_dir()
                else 0
            )
            frontend_count = 0
            if fe_dir.is_dir():
                frontend_count = len(
                    [p for p in fe_dir.rglob("ui_manifest.json") if not p.name.startswith("_")]
                )
            be_dir = backend_dir(alias)
            backend_count = 0
            if be_dir.is_dir():
                backend_count = len(
                    [p for p in be_dir.rglob("api_manifest.json") if not p.name.startswith("_")]
                )
            manifest = read_manifest(alias)
            form = project_setup_form_from_config(alias, raw)
            source_files = list_source_files(alias, verify_disk=True)
            projects.append(
                {
                    **form,
                    "source_files": source_files,
                    "source_file_count": len(source_files),
                    "dataset_count": dataset_count,
                    "frontend_count": frontend_count,
                    "backend_count": backend_count,
                    "updated_at": raw.get("updated_at") or manifest.get("updated_at", ""),
                    "is_active": alias == active,
                }
            )
        except (json.JSONDecodeError, OSError, ValueError):
            continue

    active_list = [p for p in projects if p.get("is_active")]
    rest = [p for p in projects if not p.get("is_active")]
    rest.sort(key=lambda p: p.get("updated_at", "") or "", reverse=True)
    return active_list + rest


def select_project(db_alias: str) -> dict[str, Any]:
    """切换当前工作项目（不修改配置）。"""
    alias = validate_db_alias(db_alias)
    if not config_path(alias).is_file():
        raise FileNotFoundError(f"saas {alias} 尚无配置，请先完成初始化")
    save_studio_state(alias)
    return get_status()


def clear_studio_state() -> None:
    """清空 Studio 当前选中的 saas 与会话。"""
    STUDIO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STUDIO_STATE_PATH.write_text("{}", encoding="utf-8")


def upload_project_source_files(db_alias: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    if not config_path(alias).is_file():
        raise FileNotFoundError(f"saas 不存在: {alias}，请先保存配置")
    return upload_source_files(alias, files)


def remove_project_source_file(db_alias: str, rel_path: str) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    if not config_path(alias).is_file():
        raise FileNotFoundError(f"saas 不存在: {alias}")
    return _delete_source_file(alias, rel_path)


def delete_project(db_alias: str) -> dict[str, Any]:
    """删除 saas 工作区（含前端、后端、对话、本地 SQLite 等）。"""
    import shutil

    from skill_package.workspace.paths import WORKSPACE_ROOT, workspace_dir
    from studio.backend_runner import stop_backends_for_alias

    alias = validate_db_alias(db_alias)
    cfg_file = config_path(alias)
    if not cfg_file.is_file():
        raise FileNotFoundError(f"saas 不存在: {alias}")

    ws = workspace_dir(alias)
    root = WORKSPACE_ROOT.resolve()
    if root not in ws.parents:
        raise ValueError(f"非法工作区路径: {alias}")

    stopped_backends = stop_backends_for_alias(alias)
    state = load_studio_state()
    was_active = state.get("db_alias") == alias

    shutil.rmtree(ws)

    if was_active:
        clear_studio_state()

    return {
        "ok": True,
        "db_alias": alias,
        "was_active": was_active,
        "stopped_backends": stopped_backends,
        "remaining_count": len(list_projects()),
        "status": get_status() if was_active else None,
    }


def get_project_setup_form(db_alias: str) -> dict[str, Any]:
    """读取项目配置用于编辑表单（不含密码明文）。"""
    alias = validate_db_alias(db_alias)
    path = config_path(alias)
    if not path.is_file():
        raise FileNotFoundError(f"saas 不存在: {alias}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"saas 配置格式无效: {alias}")
    form = project_setup_form_from_config(alias, raw)
    form["source_files"] = list_source_files(alias, verify_disk=True)
    return form


def load_studio_state() -> dict[str, Any]:
    if not STUDIO_STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STUDIO_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _studio_skill_visible(metadata: dict[str, Any], *, origin: str = "system") -> bool:
    """SKILL.md frontmatter：studio_visible: false 时不在对话中自动启用。"""
    if origin == "custom" and "studio_visible" not in metadata:
        return True
    raw = metadata.get("studio_visible", metadata.get("studio", True))
    if raw is False:
        return False
    if isinstance(raw, str) and raw.strip().lower() in ("false", "0", "no", "off"):
        return False
    return True


def _skill_display_path(skill_id: str, origin: str) -> str:
    if origin == "custom":
        return f"config/custom_skills/{skill_id}"
    return f"skill_package/skills/{skill_id}"


def _resolve_studio_skill(skill_id: str) -> tuple[str, Skill]:
    """Studio 读写优先使用 config/custom_skills/ 磁盘目录（与 orchestrator 是否撞名无关）。"""
    sid = validate_skill_id(str(skill_id).strip())
    custom_path = iter_custom_skill_dirs()
    for d in custom_path:
        if d.name == sid:
            return sid, Skill(skill_id=sid, path=d, origin="custom")
    orch = skill_caller.orchestrator
    orch.refresh_skills()
    if sid in orch.skills:
        return sid, orch.skills[sid]
    raise FileNotFoundError(f"skill 不存在: {sid}")


def _get_skill_record(skill_id: str):
    return _resolve_studio_skill(skill_id)


def _assert_skill_editable(skill_id: str):
    sid, sk = _get_skill_record(skill_id)
    if sk.read_only:
        raise PermissionError("系统 skill 不可修改")
    return sid, sk


def _studio_skill_order(metadata: dict[str, Any], skill_id: str) -> tuple[int, str]:
    raw = metadata.get("studio_order", metadata.get("order", 9999))
    try:
        return (int(raw), skill_id)
    except (TypeError, ValueError):
        return (9999, skill_id)


def _studio_skill_list_row(
    skill_id: str,
    sk: Skill,
    *,
    include_hidden: bool,
) -> dict[str, Any] | None:
    from skill_package.core.registry import SKILL_TOOL_REGISTRY

    meta = dict(sk.metadata) if isinstance(sk.metadata, dict) else {}
    visible = _studio_skill_visible(meta, origin=sk.origin)
    if not include_hidden and not visible:
        return None
    if sk.origin == "system":
        skill_caller.orchestrator.ensure_tools_loaded(skill_id)
    tool_count = sum(1 for t in SKILL_TOOL_REGISTRY.values() if t.skill_id == skill_id)
    desc = (sk.description or "").strip().replace("\n", " ")
    if len(desc) > 240:
        desc = desc[:237] + "..."
    return {
        "id": skill_id,
        "name": sk.name,
        "description": desc,
        "version": str(meta.get("version") or ""),
        "studio_visible": visible,
        "origin": sk.origin,
        "read_only": sk.read_only,
        "editable": not sk.read_only,
        "tool_count": tool_count,
        "path": _skill_display_path(skill_id, sk.origin),
        "order": _studio_skill_order(meta, skill_id)[0],
    }


def list_studio_skills(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    """系统 skill 来自 skill_package/skills；自定义 skill 始终扫描 config/custom_skills 磁盘。"""
    orch = skill_caller.orchestrator
    orch.refresh_skills()
    items: list[dict[str, Any]] = []
    custom_ids: set[str] = set()

    for d in iter_custom_skill_dirs():
        sk = Skill(skill_id=d.name, path=d, origin="custom")
        custom_ids.add(d.name)
        row = _studio_skill_list_row(d.name, sk, include_hidden=include_hidden)
        if row:
            items.append(row)

    for skill_id, sk in orch.skills.items():
        if sk.origin != "system":
            continue
        row = _studio_skill_list_row(skill_id, sk, include_hidden=include_hidden)
        if row:
            items.append(row)

    items.sort(key=lambda x: (x.get("order", 9999), x["id"]))
    for row in items:
        row.pop("order", None)
    return items


def _skill_files_list(skill_path: Path, *, read_only: bool = False) -> list[dict[str, Any]]:
    from studio.artifacts import _is_text_file

    root = skill_path.resolve()
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        editable = _is_text_file(p) and not read_only
        out.append({"path": rel, "editable": editable})
    return out


def _resolve_skill_relative_path(
    skill_id: str, rel_path: str, *, must_exist: bool = True
) -> tuple[str, Path, Path]:
    sid, sk = _resolve_studio_skill(skill_id)
    rel = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError(f"非法文件路径: {rel_path!r}")
    root = sk.path.resolve()
    path = (root / rel).resolve()
    if root not in path.parents:
        raise ValueError("文件路径须位于 skill 目录内")
    if must_exist and not path.exists():
        raise FileNotFoundError(f"路径不存在: {rel}")
    return sid, root, path


def _resolve_skill_file_path(skill_id: str, rel_path: str) -> tuple[str, Path, Path]:
    sid, root, path = _resolve_skill_relative_path(skill_id, rel_path, must_exist=True)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {rel_path}")
    return sid, root, path


def get_skill_file(skill_id: str, rel_path: str) -> dict[str, Any]:
    from studio.artifacts import MAX_FILE_BYTES, _is_text_file

    sid, sk = _get_skill_record(skill_id)
    _, root, path = _resolve_skill_file_path(skill_id, rel_path)
    rel = path.relative_to(root).as_posix()
    editable = _is_text_file(path) and not sk.read_only
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"文件过大（>{MAX_FILE_BYTES // (1024 * 1024)}MB），无法在 Studio 中打开")
    content = path.read_text(encoding="utf-8") if editable else ""
    return {
        "skill_id": sid,
        "path": rel,
        "editable": editable,
        "read_only": sk.read_only,
        "origin": sk.origin,
        "size": size,
        "content": content,
    }


def save_skill_file(skill_id: str, rel_path: str, content: str) -> dict[str, Any]:
    from studio.artifacts import MAX_FILE_BYTES, _is_text_file

    _assert_skill_editable(skill_id)
    sid, root, path = _resolve_skill_file_path(skill_id, rel_path)
    rel = path.relative_to(root).as_posix()
    if not _is_text_file(path):
        raise ValueError("该文件类型不支持在线编辑")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"内容过大（>{MAX_FILE_BYTES // (1024 * 1024)}MB）")

    path.write_text(content, encoding="utf-8")

    if rel == "SKILL.md":
        skill_caller.orchestrator.skills[sid]._load()

    return {
        "skill_id": sid,
        "path": rel,
        "saved": True,
        "size": path.stat().st_size,
    }


def create_skill_file(skill_id: str, rel_path: str, content: str = "") -> dict[str, Any]:
    from studio.artifacts import MAX_FILE_BYTES, _is_text_file

    _assert_skill_editable(skill_id)
    sid, root, path = _resolve_skill_relative_path(skill_id, rel_path, must_exist=False)
    rel = str(rel_path).strip().replace("\\", "/").lstrip("/")
    if path.exists():
        raise ValueError(f"文件已存在: {rel}")
    if not _is_text_file(path):
        raise ValueError("不支持的文件类型")
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError(f"内容过大（>{MAX_FILE_BYTES // (1024 * 1024)}MB）")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if rel == "SKILL.md":
        skill_caller.orchestrator.skills[sid]._load()
    return {"skill_id": sid, "path": rel, "created": True}


def delete_skill_path(skill_id: str, rel_path: str) -> dict[str, Any]:
    import shutil

    _assert_skill_editable(skill_id)
    sid, root, path = _resolve_skill_relative_path(skill_id, rel_path, must_exist=True)
    rel = path.relative_to(root).as_posix()
    is_dir = path.is_dir()
    affects_skill_md = rel == "SKILL.md"
    if is_dir:
        affects_skill_md = (path / "SKILL.md").exists() or any(
            p.name == "SKILL.md" for p in path.rglob("*") if p.is_file()
        )
    if is_dir:
        shutil.rmtree(path)
    else:
        path.unlink()
    if affects_skill_md:
        skill_caller.orchestrator.skills[sid]._load()
    return {"skill_id": sid, "path": rel, "deleted": True, "is_dir": is_dir}


def get_studio_skill_detail(skill_id: str) -> dict[str, Any]:
    """读取 skill 详情：SKILL.md 正文、工具列表、目录文件。"""
    from skill_package.core.registry import SKILL_TOOL_REGISTRY

    sid, sk = _resolve_studio_skill(skill_id)
    if sk.origin == "system":
        skill_caller.orchestrator.ensure_tools_loaded(sid)
    sk._load()

    tools: list[dict[str, Any]] = []
    labels = list_tool_labels()
    for tool in sorted(SKILL_TOOL_REGISTRY.values(), key=lambda t: t.name):
        if tool.skill_id != sid:
            continue
        fn = tool.schema.get("function") if isinstance(tool.schema, dict) else {}
        fn = fn if isinstance(fn, dict) else {}
        desc = str(fn.get("description") or "").strip()
        tools.append(
            {
                "name": tool.name,
                "label": labels.get(tool.name, tool.name),
                "description": desc,
                "aliases": list(tool.alias),
            }
        )

    meta = dict(sk.metadata) if isinstance(sk.metadata, dict) else {}
    visible = _studio_skill_visible(meta, origin=sk.origin)
    display_path = _skill_display_path(sid, sk.origin)
    return {
        "id": sid,
        "name": sk.name,
        "description": (sk.description or "").strip(),
        "version": str(meta.get("version") or ""),
        "studio_visible": visible,
        "origin": sk.origin,
        "read_only": sk.read_only,
        "editable": not sk.read_only,
        "path": display_path,
        "skill_md_path": f"{display_path}/SKILL.md",
        "instructions": sk.instructions,
        "metadata": meta,
        "tools": tools,
        "files": _skill_files_list(sk.path, read_only=sk.read_only),
    }


def create_skill_author_session() -> dict[str, Any]:
    sid = new_session_id()
    return {"session_id": sid}


def upload_skill_author_files(session_id: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    sid = validate_session_id(session_id)
    saved: list[dict[str, Any]] = []
    for name, data in files:
        saved.append(save_skill_author_upload(sid, name, data))
    return {"session_id": sid, "files": saved, "all": list_skill_author_uploads(sid)}


def list_skill_author_session_files(session_id: str) -> dict[str, Any]:
    sid = validate_session_id(session_id)
    return {"session_id": sid, "files": list_skill_author_uploads(sid)}


def upload_custom_skill_zip(data: bytes, skill_id: str | None = None) -> dict[str, Any]:
    result = extract_custom_skill_zip(data, skill_id=skill_id)
    skill_caller.orchestrator.refresh_skills()
    sid = str(result.get("skill_id") or "")
    if sid:
        try:
            detail = get_studio_skill_detail(sid)
            result["skill"] = {
                "id": detail["id"],
                "name": detail["name"],
                "description": detail.get("description") or "",
                "version": detail.get("version") or "",
                "studio_visible": detail.get("studio_visible", True),
                "origin": "custom",
                "read_only": False,
                "editable": True,
                "tool_count": len(detail.get("tools") or []),
                "path": detail.get("path") or f"config/custom_skills/{sid}",
            }
        except Exception:
            pass
    return result


def upload_custom_skill_folder(
    files: list[tuple[str, bytes]], skill_id: str | None = None
) -> dict[str, Any]:
    result = import_custom_skill_files(files, skill_id=skill_id)
    skill_caller.orchestrator.refresh_skills()
    sid = str(result.get("skill_id") or "")
    system_ids = {
        k for k, v in skill_caller.orchestrator.skills.items() if v.origin == "system"
    }
    if sid and sid in system_ids:
        result["warning"] = (
            f"skill_id「{sid}」与系统 Skill 重名：文件已写入 config/custom_skills/{sid}/，"
            "请在「自定义」列表查看（不会出现在「系统」列表）。"
        )
    if sid:
        try:
            detail = get_studio_skill_detail(sid)
            result["skill"] = {
                "id": detail["id"],
                "name": detail["name"],
                "description": detail.get("description") or "",
                "version": detail.get("version") or "",
                "studio_visible": detail.get("studio_visible", True),
                "origin": "custom",
                "read_only": False,
                "editable": True,
                "tool_count": len(detail.get("tools") or []),
                "path": detail.get("path") or f"config/custom_skills/{sid}",
            }
        except Exception:
            pass
    return result


def delete_custom_skill(skill_id: str) -> dict[str, Any]:
    sid, sk = _get_skill_record(skill_id)
    if sk.origin != "custom":
        raise PermissionError("仅可删除自定义 skill")
    result = _delete_custom_skill_dir(sid)
    skill_caller.orchestrator.refresh_skills()
    return result


def list_tool_labels() -> dict[str, str]:
    """全部已注册工具的中文展示名（含别名）。"""
    orch = skill_caller.orchestrator
    orch.refresh_skills()
    orch.ensure_all_visible_tools_loaded()
    return get_tool_display_labels()


def get_status() -> dict[str, Any]:
    state = load_studio_state()
    db_alias = state.get("db_alias", "")
    llm_provider = "deepseek"
    has_deepseek = False
    has_gemini = False
    llm_ready = False
    deepseek_error = ""
    gemini_model = "gemini-2.0-flash"
    try:
        load_deepseek_config()
        has_deepseek = True
    except Exception as e:
        deepseek_error = str(e)

    has_db = bool(db_alias) and config_path(db_alias).is_file() if db_alias else False
    source_databases: list[str] = []
    target_database = ""
    storage_mode = ""
    config_ok = False
    source_files: list[dict[str, Any]] = []
    if has_db:
        try:
            cfg = load_workspace_config(db_alias)
            source_databases = cfg.get("source_databases", [])
            target_database = cfg.get("target_database", "")
            storage_mode = cfg.get("storage_mode", "")
            source_files = cfg.get("source_files", [])
            config_ok = True
            llm = workspace_llm_status(db_alias, cfg)
            llm_provider = llm["llm_provider"]
            has_gemini = llm["has_gemini"]
            llm_ready = llm["llm_ready"]
            gemini_model = llm["gemini_model"]
        except Exception:
            pass

    if has_db and config_ok and not llm_ready and llm_provider == "deepseek":
        llm_ready = has_deepseek

    ready = llm_ready and has_db and bool(db_alias) and config_ok

    return {
        "ready": ready,
        "db_alias": db_alias,
        "conversation_id": state.get("conversation_id", ""),
        "source_databases": source_databases,
        "source_files": source_files,
        "target_database": target_database,
        "storage_mode": storage_mode,
        "llm_provider": llm_provider,
        "has_deepseek": has_deepseek,
        "has_gemini": has_gemini,
        "llm_ready": llm_ready,
        "gemini_model": gemini_model,
        "has_db_config": has_db,
        "deepseek_config_path": str(DEFAULT_CONFIG_PATH),
        "workspace_config_path": str(config_path(db_alias)) if db_alias else "",
        "deepseek_error": deepseek_error,
        "projects": list_projects(),
        "skills": list_studio_skills(),
    }


def complete_setup(
    *,
    db_alias: str,
    host: str,
    port: int,
    user: str,
    password: str,
    source_databases: list[str],
    target_database: str,
    deepseek_api_key: str | None = None,
    target_user: str | None = None,
    target_password: str | None = None,
    deepseek_base_url: str = "https://api.deepseek.com",
    deepseek_model: str = "deepseek-chat",
    llm_provider: str = "deepseek",
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-2.0-flash",
    test_connection: bool = True,
) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    sources = [s.strip() for s in source_databases if s.strip()]
    target = target_database.strip()
    if target and target in sources:
        raise ValueError("目标库不能与源库重名")

    needs_mysql = bool(sources) or bool(target)

    existing: dict[str, Any] | None = None
    cfg_file = config_path(alias)
    if cfg_file.is_file():
        existing = json.loads(cfg_file.read_text(encoding="utf-8"))

    final_password = password.strip() if password else str((existing or {}).get("password") or "")
    if needs_mysql:
        if not final_password or is_redacted_secret(final_password):
            raise ValueError("连接 MySQL 时须填写源库密码（编辑 saas 时留空则保留原密码）")

    tgt_pwd = (
        target_password.strip()
        if target_password and str(target_password).strip()
        else (existing or {}).get("target_password") or final_password
    )

    has_deepseek = False
    try:
        load_deepseek_config()
        has_deepseek = True
    except Exception:
        pass

    provider = normalize_llm_provider(
        llm_provider or (existing or {}).get("llm_provider") or "deepseek"
    )
    gemini_key_new = (gemini_api_key or "").strip()
    has_gemini_ws = bool(str((existing or {}).get("gemini_api_key") or "").strip()) and not is_redacted_secret(
        (existing or {}).get("gemini_api_key")
    )

    if deepseek_api_key and deepseek_api_key.strip():
        save_deepseek_config(
            api_key=deepseek_api_key.strip(),
            base_url=deepseek_base_url,
            model=deepseek_model,
        )
        has_deepseek = True

    if provider == "gemini":
        if not gemini_key_new and not has_gemini_ws:
            try:
                from agents.llm_config import load_gemini_global_config

                load_gemini_global_config()
            except Exception:
                raise ValueError("Please enter Gemini API Key (or add config/gemini.json)")
    elif not has_deepseek:
        raise ValueError("Please enter DeepSeek API Key")

    if test_connection and needs_mysql:
        if sources:
            for db in sources:
                test_mysql_connection(
                    host=host,
                    port=port,
                    user=user,
                    password=final_password,
                    database=db,
                    role="源库",
                )
        if target:
            test_mysql_connection(
                host=host,
                port=port,
                user=target_user or user,
                password=tgt_pwd,
                database=target,
                role="目标库",
            )

    db_result = save_workspace_config(
        db_alias=alias,
        host=(host or "127.0.0.1").strip(),
        port=int(port),
        user=(user or "").strip(),
        password=final_password or "",
        source_databases=sources,
        target_database=target,
        target_user=target_user,
        target_password=tgt_pwd if needs_mysql else None,
        llm_provider=provider,
        gemini_api_key=gemini_key_new or None,
        gemini_model=gemini_model,
    )
    save_studio_state(alias)
    source_files = list_source_files(alias, verify_disk=True)
    return {
        "ok": True,
        "db_alias": alias,
        "source_databases": sources,
        "source_files": source_files,
        "target_database": target,
        "storage_mode": db_result.get("storage_mode"),
        "workspace": f"skill_package/workspace/{alias}/",
        "deepseek_config": str(DEFAULT_CONFIG_PATH),
        "database_save": db_result,
    }


def prepare_skill(skill_id: str) -> tuple[str, list[dict[str, Any]]]:
    return prepare_skills([skill_id])


def prepare_skills(skill_ids: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """加载一个或多个 skill 的上下文，并合并工具 schema。"""
    orch = skill_caller.orchestrator
    orch.refresh_skills()

    ids: list[str] = []
    for raw in skill_ids:
        sid = str(raw).strip()
        if not sid or sid in ids:
            continue
        if sid not in orch.skills:
            available = ", ".join(orch.skills.keys()) or "（无）"
            raise ValueError(f"未知 skill: {sid!r}。当前可用: {available}")
        ids.append(sid)

    if not ids:
        raise ValueError("请至少选择一个 skill")

    contexts: list[tuple[str, str]] = []
    for sid in ids:
        orch.ensure_tools_loaded(sid)
        result = skill_caller.invoke(sid)
        contexts.append((sid, result.context))

    if len(ids) == 1:
        context = contexts[0][1]
    else:
        blocks = [f"## Skill: {sid}\n\n{ctx}" for sid, ctx in contexts]
        context = (
            "你同时启用了以下 skill，请综合运用各 skill 的说明与工具完成任务；"
            "若不同 skill 的规则冲突，以与用户问题最相关的 skill 为准。\n\n"
            + "\n\n---\n\n".join(blocks)
        )

    tools = get_tool_schemas_for_skills(ids)
    return context, tools


def _output_style_guard() -> str:
    """约束模型勿向用户输出推理独白（与工具调用记录分开展示）。"""
    return (
        "\n【输出风格（必须遵守）】\n"
        "- 面向用户写**结论与操作结果**，不要写推理过程、内心独白或「自言自语」。\n"
        "- **禁止**英文口语独白（如 Wait、Let me check、I see、Possibility 1）及中英混杂的推演段落。\n"
        "- **禁止**「让我检查…」「等等，我发现…」「有两种可能…」等元叙述；要查代码或改文件时**直接调用工具**，无需事先向用户预告。\n"
        "- 工具调用由界面单独展示；你的正文只在**工具执行完毕后**用简洁中文说明：做了什么、结果如何、文件路径、用户下一步。\n"
        "- 单轮回复宜精炼，避免重复已说过的内容；技术细节写进文件，对话里只保留摘要。\n"
    )


def _skill_reply_requirements(skill_ids: list[str]) -> str:
    """各 skill 共用的「工具调用后必须向用户说明」约束。"""
    lines = [
        "\n【对话回复要求】",
        "工具全部执行完后，用中文向用户说明实际完成了什么，不能只停在工具调用。",
        "回复须包含：关键结论、修改摘要、产物路径（workspace 下相对路径）。",
        "禁止编造未写入磁盘的路径或文件；声称某目录/页面已存在前，须用 check_* / list_* / verify_fullstack_deliverables 核实。",
    ]
    if "UI_build" in skill_ids:
        lines.extend(
            [
                "【UI_build 专项】生成或修改前端后须说明：",
                "- 工程目录 frontend/{saas名}/ 与主要文件；",
                "- 是否已写入/更新 ui_knowledge.md；",
                "- 是否有 preview.html 可在 Studio「后台文件」→「预览」查看；",
                "- 本地运行方式（如 npm run dev）若适用。",
            ]
        )
    if "database" in skill_ids:
        lines.append(
            "【database 专项】整理库表后须说明 dataset/ 下文档路径与覆盖范围。"
        )
    if "backend" in skill_ids:
        lines.extend(
            [
                "【backend 专项】生成或修改后端后须说明：",
                "- 工程目录 backend/{saas名}/ 与主要路由文件；",
                "- 是否已写入/更新 api_knowledge.md；",
                "- 启动命令（uvicorn）与 API 基址（如 http://127.0.0.1:8000/api）；",
                "- 关联的 frontend 工程名；若前端尚未创建，须明确提示继续 UI_build，不得代写前端代码路径。",
            ]
        )
    if "backend" in skill_ids and "UI_build" in skill_ids:
        lines.append(
            "【全栈收尾】新建系统用 scaffold_fullstack_project；写盘违规会 blocked；"
            "verify_fullstack_deliverables.system_complete 为 true 才能说系统可运行。"
        )
    if "skill_author" in skill_ids:
        lines.extend(
            [
                "【skill_author 专项】与用户确认 skill_id 与正文后再 create_custom_skill；",
                "创建成功后说明路径 config/custom_skills/{skill_id}/ 及如何在 Skill 库查看。",
            ]
        )
    return "\n".join(lines) + "\n"


def _workspace_chat_prefix(alias: str) -> str:
    try:
        cfg = load_workspace_config(alias)
        sources = cfg.get("source_databases", [])
        target = cfg.get("target_database", "")
        storage = cfg.get("storage_mode", "mysql")
        if storage == "local":
            local_path = cfg.get("local_sqlite_path") or DEFAULT_LOCAL_SQLITE_REL
            target_line = (
                f"- 持久化：本地 SQLite workspace/{alias}/{local_path} "
                f"（connection_mode=target，无 MySQL 目标库）\n"
            )
        else:
            target_line = (
                f"- 目标库 target_database（唯一可建表/写入，connection_mode=target）：{target}\n"
            )
        source_line = (
            f"- 源库 source_databases（只读整理，connection_mode=source）：{sources}\n"
            if sources
            else "- 源库 MySQL：未配置\n"
        )
        files = cfg.get("source_files") or []
        if files:
            names = [f.get("name") or f.get("path") for f in files]
            file_line = (
                f"- 源文件 source_files（xlsx/csv，list_source_files / read_source_file）：{names}\n"
            )
        else:
            file_line = "- 源文件：未上传（可仅用 MySQL 或本地 SQLite）\n"
        return (
            f"\n【工作区 db_alias={alias}】\n"
            f"{source_line}"
            f"{file_line}"
            f"{target_line}"
            f"- 连接请用 database_connect(use_workspace_config=true, ...)；工具会从磁盘 config.json 读取真实密码，无需向用户索要\n"
            f"- read_database_config 返回的 password 为 *** 仅为脱敏展示，禁止据此向用户要密码\n"
            f"- 若 host/user 为空，请让用户在 Studio「初始化/编辑 saas」页补全，不要聊天里收集密码\n"
            f"- 禁止对源库执行 CREATE/INSERT/UPDATE/DELETE\n\n"
        )
    except Exception:
        return f"\n【工作区 db_alias={alias}】\n\n"


def trim_chat_history(
    history: list[dict[str, str]],
    *,
    max_messages: int = 40,
) -> list[dict[str, str]]:
    """保留最近若干轮 user/assistant 消息，避免超出模型上下文。"""
    cleaned: list[dict[str, str]] = []
    for item in history:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    if len(cleaned) <= max_messages:
        return cleaned
    return cleaned[-max_messages:]


def stream_chat(
    skill_ids: list[str],
    message: str,
    history: list[dict[str, str]] | None = None,
    db_alias: str | None = None,
    *,
    mode: str = "normal",
    skill_author_session: str | None = None,
) -> Iterator[str]:
    from agents import get_agent_backend

    alias = db_alias or load_studio_state().get("db_alias") or ""
    if not alias:
        raise ValueError("未配置 db_alias，请先完成初始化设置")

    user_msg = (message or "").strip()
    if not user_msg:
        raise ValueError("消息不能为空")

    if mode == "skill_author":
        skill_ids = ["skill_author"]
        set_skill_author_session(skill_author_session)
        skill_caller.orchestrator.ensure_tools_loaded("skill_author")
    else:
        set_skill_author_session(None)

    context, tools = prepare_skills(skill_ids)
    agent = get_agent_backend(tool_runner=_run_tool, db_alias=alias)
    if mode == "skill_author":
        workspace_note = build_upload_context(skill_author_session).strip()
        if skill_author_session:
            workspace_note = (
                f"\n【Skill 创建会话】session_id={skill_author_session}\n"
                f"{workspace_note}"
            ).strip()
    else:
        workspace_note = _workspace_chat_prefix(alias).strip()
    skill_note = ""
    if len(skill_ids) > 1:
        skill_note = f"\n【当前启用 skill】{', '.join(skill_ids)}\n"
    reply_note = _skill_reply_requirements(skill_ids)
    tool_note = ""
    if mode != "skill_author":
        tool_note = (
            f"\n【工具调用】当前工作区 db_alias={alias}。"
            "已有文件的小修改优先 patch_*_file（old_string/new_string），新建或大改用 save_*_file。"
        )
    elif skill_author_session:
        tool_note = (
            f"\n【工具调用】Skill 创建会话 session_id={skill_author_session}；"
            "读取用户上传文件用 list_skill_author_uploads / read_skill_author_upload；"
            "落盘自定义 Skill 用 create_custom_skill / write_custom_skill_file。\n"
        )
    if "UI_build" in skill_ids:
        tool_note += (
            "save_ui_file 须含 project_name、file_path、content；"
            "写入 JS 时请让页面通过 API 拉取真实库表数据。\n"
        )
    else:
        tool_note += "\n"
    orchestration_note = build_fullstack_orchestration_note(skill_ids)
    # 输出风格约束放在最前，降低被 skill 长文稀释的概率
    system_prompt = (
        f"{_output_style_guard()}\n{context}\n{workspace_note}{skill_note}"
        f"{tool_note}{orchestration_note}{reply_note}"
    ).strip()

    prior = trim_chat_history(list(history or []))
    yield from agent.chat(
        system_prompt,
        user_msg,
        history=prior,
        tools=tools,
    )
