"""全栈生成硬性规范：写盘前校验，不通过则拒绝保存（保证系统能启动、能对接）。"""

from __future__ import annotations

import json
import re
from typing import Any

SPEC_VERSION = "1.0"

# 供 agent / 工具返回引用的规范摘要
GENERATION_SPEC: dict[str, Any] = {
    "version": SPEC_VERSION,
    "priority": "可运行 > 功能完整 > 美观",
    "mandatory_order": [
        "database（表结构 / dataset）",
        "scaffold_fullstack_project 或按模板新建 backend + frontend",
        "backend：routers + api_knowledge.md",
        "get_fullstack_api_contract",
        "UI_build：preview.html 业务逻辑（只用 apiGet/apiPost）",
        "verify_fullstack_deliverables（system_complete 必须为 true）",
    ],
    "backend_rules": [
        "api_manifest.api_prefix 必须为 \"/api\"",
        "api_manifest.linked_frontend 必填，等于 frontend 目录名",
        "main.py 须有 app = FastAPI 与 app.include_router",
        "业务路由统一 APIRouter(prefix=\"/api/...\") 或 api_router(prefix=\"/api\")",
        "禁止 add_api_route 注册无前缀业务路由（禁止双轨兼容）",
        "禁止任何 .py 使用 from . / from .. 相对导入",
        "须有 GET /api/health 返回 {\"ok\": true}",
        "requirements.txt 须含 fastapi、uvicorn",
    ],
    "frontend_rules": [
        "须有 preview.html 与 ui_manifest.json",
        "禁止 const API、禁止硬编码 http://127.0.0.1:8xxx",
        "数据请求只用 apiGet/apiPost/apiPut/apiDel（FULLSTACK_API 块提供）",
        "apiGet 的 path 须出现在 get_fullstack_api_contract.route_fetch_map",
        "api_prefix 为 /api 时 path 不要再以 /api 开头",
    ],
    "completion_gate": "verify_fullstack_deliverables.system_complete === true",
}

_REL_IMPORT = re.compile(r"^\s*from\s+(\.+)([\w.]*)\s*import\s+", re.M)
_HARDCODED_API = re.compile(r"https?://(?:127\.0\.0\.1|localhost):80\d{2}", re.I)
_API_VAR = re.compile(r"(?:var|const|let)\s+API\s*=", re.I)
_DUAL_ROUTE = re.compile(r'add_api_route\s*\(\s*["\']/(?!api/)', re.I)
_ROOT_HEALTH = re.compile(r'@app\.get\s*\(\s*["\']/health["\']', re.I)


def spec_summary_text() -> str:
    lines = [f"全栈生成规范 v{SPEC_VERSION}（硬性）", ""]
    for i, step in enumerate(GENERATION_SPEC["mandatory_order"], 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("后端：" + "；".join(GENERATION_SPEC["backend_rules"][:4]) + "…")
    lines.append("收尾：" + GENERATION_SPEC["completion_gate"])
    return "\n".join(lines)


def validate_api_manifest_content(content: str) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return [f"api_manifest.json 不是合法 JSON: {e}"]
    if not isinstance(data, dict):
        return ["api_manifest.json 须为 JSON 对象"]
    if not data.get("has_database_connection"):
        errors.append("has_database_connection 须为 true")
    prefix = str(data.get("api_prefix") if data.get("api_prefix") is not None else "")
    if prefix != "/api":
        errors.append('api_prefix 必须为 "/api"（全栈规范不允许其它值）')
    if not str(data.get("linked_frontend") or "").strip():
        errors.append("linked_frontend 必填（前端工程目录名）")
    if "（" in prefix or "）" in prefix or " " in prefix:
        errors.append("api_prefix 不能包含说明文字")
    port = data.get("default_port", 8000)
    try:
        if not (1024 <= int(port) <= 65535):
            errors.append("default_port 须在 1024–65535")
    except (TypeError, ValueError):
        errors.append("default_port 须为整数")
    return errors


def validate_backend_python(rel_path: str, content: str) -> list[str]:
    errors: list[str] = []
    if _REL_IMPORT.search(content):
        errors.append(
            f"{rel_path} 含相对导入；须改为绝对导入（如 from routers import xxx、from database import xxx）"
        )
    if rel_path == "main.py":
        if "app = FastAPI" not in content and "app=FastAPI" not in content:
            errors.append("main.py 须定义 app = FastAPI(...)")
        if "include_router" not in content:
            errors.append("main.py 须 app.include_router(...) 注册路由")
        if _DUAL_ROUTE.search(content):
            errors.append(
                "main.py 禁止 add_api_route 无前缀业务路由；删除兼容探测代码，统一使用 /api 前缀"
            )
        if _ROOT_HEALTH.search(content) and (
            'prefix="/api"' in content or "prefix='/api'" in content
        ):
            errors.append(
                'main.py 禁止 @app.get("/health") 与 /api 双轨；仅保留 @api_router.get("/health")'
            )
        try:
            compile(content, rel_path, "exec")
        except SyntaxError as e:
            errors.append(f"main.py 语法错误: {e.msg} (line {e.lineno})")
    return errors


def validate_preview_html(content: str) -> list[str]:
    """写盘前拦截明显会导致无法对接的 preview 写法。"""
    errors: list[str] = []
    if _API_VAR.search(content):
        errors.append("禁止 const API；使用 FULLSTACK_API 块提供的 apiGet/apiPost")
    if _HARDCODED_API.search(content):
        errors.append("禁止硬编码 127.0.0.1:8xxx；由 FULLSTACK_API 块管理 API_BASE")
    if re.search(r"(?:fetch|apiGet|apiPost)\s*\(\s*['\"]/api/", content, re.I):
        errors.append('api_prefix 为 /api 时，apiGet 路径不要以 "/api/" 开头')
    return errors


def validate_requirements_content(content: str) -> list[str]:
    body = content.lower()
    errors: list[str] = []
    if "fastapi" not in body:
        errors.append("requirements.txt 须包含 fastapi")
    if "uvicorn" not in body:
        errors.append("requirements.txt 须包含 uvicorn")
    return errors


def blocking_errors_for_backend_file(
    rel_path: str,
    content: str,
    *,
    after_autofix: bool = False,
) -> list[str]:
    rel = rel_path.strip().lstrip("/")
    if rel == API_MANIFEST_NAME:
        return validate_api_manifest_content(content)
    if rel == "requirements.txt":
        return validate_requirements_content(content)
    if rel.endswith(".py"):
        return validate_backend_python(rel, content)
    return []


API_MANIFEST_NAME = "api_manifest.json"
