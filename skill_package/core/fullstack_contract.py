"""全栈前后端 API 契约：skill 生成时代码对齐的唯一标准（不依赖 Studio 运行时修补）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skill_package.workspace.paths import backend_dir, frontend_dir, validate_db_alias

API_MANIFEST = "api_manifest.json"
UI_MANIFEST = "ui_manifest.json"
MARKER_BEGIN = "/* === FULLSTACK_API_BEGIN — 由 skill 工具维护，勿删 === */"
MARKER_END = "/* === FULLSTACK_API_END === */"

_ROUTER_PREFIX_RE = re.compile(
    r'APIRouter\s*\(\s*[^)]*prefix\s*=\s*["\']([^"\']+)["\']',
    re.I,
)
_ROUTE_DECORATOR_RE = re.compile(
    r"@(?:app|[\w_]+)\.(?:get|post|put|delete|patch|head|options)\(\s*[\"']([^\"']*)[\"']",
    re.I,
)
_REL_IMPORT_RE = re.compile(r"^\s*from\s+(\.+)([\w.]*)\s*import\s+", re.M)
_HARDCODED_PORT_RE = re.compile(
    r"https?://(?:127\.0\.0\.1|localhost):80\d{2}",
    re.I,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _normalize_prefix(raw: Any) -> str:
    prefix = str(raw if raw is not None else "/api").strip()
    if not prefix or prefix == '""':
        return ""
    if not prefix.startswith("/") or "（" in prefix or "）" in prefix or " " in prefix:
        return "/api"
    return prefix.rstrip("/")


def _scan_backend_projects(alias: str) -> list[dict[str, Any]]:
    root = backend_dir(alias)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for mp in root.rglob(API_MANIFEST):
        if "_template" in mp.parts:
            continue
        proj_dir = mp.parent
        meta = _read_json(mp) or {}
        if not meta.get("has_database_connection"):
            continue
        rows.append(
            {
                "project_name": proj_dir.relative_to(root).as_posix(),
                "proj_dir": proj_dir,
                "meta": meta,
            }
        )
    return sorted(rows, key=lambda r: r["project_name"])


def _scan_frontend_projects(alias: str) -> list[dict[str, Any]]:
    root = frontend_dir(alias)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for mp in root.rglob(UI_MANIFEST):
        if "_template" in mp.parts:
            continue
        proj_dir = mp.parent
        meta = _read_json(mp) or {}
        if not meta.get("has_database_connection"):
            continue
        rows.append(
            {
                "project_name": proj_dir.relative_to(root).as_posix(),
                "proj_dir": proj_dir,
                "meta": meta,
            }
        )
    return sorted(rows, key=lambda r: r["project_name"])


def resolve_fullstack_pair(
    db_alias: str,
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    """解析 frontend ↔ backend 关联对。"""
    alias = validate_db_alias(db_alias)
    backends = _scan_backend_projects(alias)
    frontends = _scan_frontend_projects(alias)
    if not backends:
        raise ValueError(f"工作区 {alias} 尚无接库后端（backend/*/api_manifest.json）")
    if not frontends:
        raise ValueError(f"工作区 {alias} 尚无接库前端（frontend/*/ui_manifest.json）")

    be_row: dict[str, Any] | None = None
    fe_row: dict[str, Any] | None = None

    if backend_project:
        be_row = next((b for b in backends if b["project_name"] == backend_project), None)
        if not be_row:
            raise ValueError(f"后端工程不存在: backend/{backend_project}")
        linked = str(be_row["meta"].get("linked_frontend") or "").strip()
        if linked:
            fe_row = next((f for f in frontends if f["project_name"] == linked), None)
        if not fe_row and frontend_project:
            fe_row = next((f for f in frontends if f["project_name"] == frontend_project), None)
    elif frontend_project:
        fe_row = next((f for f in frontends if f["project_name"] == frontend_project), None)
        if not fe_row:
            raise ValueError(f"前端工程不存在: frontend/{frontend_project}")
        be_row = next(
            (b for b in backends if b["meta"].get("linked_frontend") == frontend_project),
            None,
        )
        if not be_row:
            be_row = next(
                (b for b in backends if b["project_name"] == frontend_project),
                None,
            )
    if not be_row and len(backends) == 1:
        be_row = backends[0]
    if not fe_row and be_row:
        linked = str(be_row["meta"].get("linked_frontend") or "").strip()
        if linked:
            fe_row = next((f for f in frontends if f["project_name"] == linked), None)
    if not fe_row and len(frontends) == 1:
        fe_row = frontends[0]

    if not be_row:
        raise ValueError("无法确定后端工程，请指定 backend_project 或先设置 api_manifest.linked_frontend")
    if not fe_row:
        raise ValueError(
            f"后端 backend/{be_row['project_name']} 的 linked_frontend 未指向前端，"
            "请 save_backend_file 更新 api_manifest.json"
        )
    return {"db_alias": alias, "backend": be_row, "frontend": fe_row}


def parse_backend_routes(proj_dir: Path) -> list[str]:
    """从 main.py 与 routers/*.py 提取对外路径（含 /api 前缀）。"""
    paths: list[str] = []
    files = [proj_dir / "main.py", *sorted(proj_dir.glob("routers/*.py"))]
    for fp in files:
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        router_prefix = ""
        m = _ROUTER_PREFIX_RE.search(text)
        if m:
            router_prefix = m.group(1).rstrip("/")
        for route in _ROUTE_DECORATOR_RE.findall(text):
            if "{" in route:
                continue
            if route in ("", "/"):
                full = router_prefix or "/"
            else:
                full = f"{router_prefix}/{route.lstrip('/')}" if router_prefix else route
            if not full.startswith("/"):
                full = "/" + full
            full = re.sub(r"/+", "/", full)
            if full not in paths:
                paths.append(full)
    return sorted(paths)


def build_api_contract(
    db_alias: str,
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    """生成前后端对接契约（agent 写 preview.html / fetch 前必须先读此结果）。"""
    pair = resolve_fullstack_pair(
        db_alias,
        frontend_project=frontend_project,
        backend_project=backend_project,
    )
    be = pair["backend"]
    fe = pair["frontend"]
    meta = be["meta"]
    proj_dir: Path = be["proj_dir"]
    port = int(meta.get("default_port") or 8000)
    api_prefix = _normalize_prefix(meta.get("api_prefix"))
    local_base = f"http://127.0.0.1:{port}{api_prefix}"
    routes = parse_backend_routes(proj_dir)
    health_fetch = "/health"
    if f"{api_prefix}/health" in routes:
        health_fetch = "/health"
    elif "/health" in routes and not api_prefix:
        health_fetch = "/health"

    gaps: list[str] = []
    linked = str(meta.get("linked_frontend") or "").strip()
    if linked != fe["project_name"]:
        gaps.append(
            f"api_manifest.linked_frontend={linked!r} 与前端目录 {fe['project_name']!r} 不一致"
        )
    if not routes:
        gaps.append("main.py / routers 中未解析到任何路由，请检查 @api_router.get 等装饰器")
    if f"{api_prefix}/health" not in routes and "/health" not in routes:
        gaps.append("缺少 GET /api/health 或 GET /health，save_backend_file 写入 main.py 时应包含健康检查")

    rel_imports = find_relative_imports_in_dir(proj_dir)
    if rel_imports:
        gaps.append(f"后端含相对导入（须改为绝对导入）: {', '.join(rel_imports[:3])}")
    gaps.extend(audit_backend_route_contract(proj_dir, meta))

    route_fetch_map = [
        {"backend_route": r, "apiGet_path": _route_suffix(r, api_prefix)}
        for r in routes
        if "{" not in r
    ]
    block = generate_preview_api_block(port=port, api_prefix=api_prefix, health_path=health_fetch)
    return {
        "ok": True,
        "db_alias": pair["db_alias"],
        "backend_project": be["project_name"],
        "frontend_project": fe["project_name"],
        "linked_frontend": fe["project_name"],
        "default_port": port,
        "api_prefix": api_prefix or "",
        "api_base_url": local_base,
        "health_fetch_path": health_fetch,
        "fetch_path_rule": (
            "API_BASE 已含 api_prefix；fetch/apiGet 的 path 不要再以 /api 开头。"
            if api_prefix
            else "api_prefix 为空；path 从 /employees 等根路径开始。"
        ),
        "backend_routes": routes,
        "route_fetch_map": route_fetch_map,
        "preview_api_block": block,
        "preview_must_include_marker": MARKER_BEGIN,
        "gaps": gaps,
        "agent_instructions": [
            "写 preview.html 前：将 preview_api_block 原样放入第一个 <script> 内（save_ui_file 会自动注入）。",
            "所有数据请求只用 apiGet/apiPost/apiPut/apiDel，禁止另写 fetch 基址或 const API。",
            f"示例：apiGet('{routes[1] if len(routes) > 1 else '/employees'}') 对应后端真实路由。",
            "backend 完成后须 save_api_knowledge 更新路由表；收尾前 verify_fullstack_deliverables。",
        ],
    }


def generate_preview_api_block(
    *,
    port: int = 8000,
    api_prefix: str = "/api",
    health_path: str = "/health",
) -> str:
    prefix = _normalize_prefix(api_prefix)
    local = f"http://127.0.0.1:{port}{prefix}"
    return f"""{MARKER_BEGIN}
const API_BASE = (window.__STUDIO_API_BASE__ || '{local}');

async function apiGet(path) {{
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}}
async function apiPost(path, body) {{
  const r = await fetch(API_BASE + path, {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
  }});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}}
async function apiPut(path, body) {{
  const r = await fetch(API_BASE + path, {{
    method: 'PUT',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
  }});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}}
async function apiDel(path) {{
  const r = await fetch(API_BASE + path, {{ method: 'DELETE' }});
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}}
async function checkBackendHealth() {{
  const el = document.getElementById('apiStatus');
  try {{
    const d = await apiGet('{health_path}');
    if (d && d.ok) {{
      if (el) {{ el.textContent = 'API 已连接'; el.className = 'status online'; }}
      return true;
    }}
  }} catch (e) {{}}
  if (el) {{
    el.textContent = 'API 未连接（' + API_BASE + '）';
    el.className = 'status';
  }}
  return false;
}}
{MARKER_END}"""


def ensure_preview_api_block(html: str, contract: dict[str, Any]) -> tuple[str, list[str]]:
    """将标准 API 层写入 preview.html（替换旧块或插入首个 script）。"""
    block = str(contract.get("preview_api_block") or "")
    if not block:
        return html, []
    changes: list[str] = []

    if MARKER_BEGIN in html and MARKER_END in html:
        pattern = re.compile(
            re.escape(MARKER_BEGIN) + r"[\s\S]*?" + re.escape(MARKER_END),
            re.M,
        )
        new_html = pattern.sub(block, html, count=1)
        if new_html != html:
            changes.append("已更新 FULLSTACK_API 标准块")
        return new_html, changes

    cleaned = html
    api_old = re.compile(r"(?:var|const|let)\s+API\s*=[^;]+;", re.I | re.M)
    base_old = re.compile(r"(?:var|const|let)\s+API_BASE\s*=[^;]+;", re.I | re.M)
    for pat in (api_old, base_old):
        if pat.search(cleaned) and MARKER_BEGIN not in cleaned:
            cleaned = pat.sub("", cleaned, count=1)
            changes.append("已移除旧的 API/API_BASE 声明（由标准块替代）")

    if "<script" in cleaned.lower():
        new_html = re.sub(
            r"(<script[^>]*>)",
            r"\1\n" + block + "\n",
            cleaned,
            count=1,
            flags=re.I,
        )
        changes.append("已在首个 <script> 注入 FULLSTACK_API 标准块")
        return new_html, changes

    insert = f"<script>\n{block}\n</script>\n"
    if "</body>" in cleaned.lower():
        new_html = re.sub(r"</body>", insert + "</body>", cleaned, count=1, flags=re.I)
    else:
        new_html = cleaned + insert
    changes.append("已追加 FULLSTACK_API 标准块")
    return new_html, changes


def find_relative_imports_in_dir(proj_dir: Path) -> list[str]:
    found: list[str] = []
    for py in proj_dir.rglob("*.py"):
        if "_template" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        if _REL_IMPORT_RE.search(text):
            found.append(py.relative_to(proj_dir).as_posix())
    return found


def fix_relative_imports(content: str) -> tuple[str, list[str]]:
    """将常见相对导入改为绝对导入（routers / database 同级工程）。"""
    changes: list[str] = []

    def _repl(m: re.Match[str]) -> str:
        dots = m.group(1)
        module = (m.group(2) or "").strip(".")
        if dots == ".":
            target = module or "routers"
            changes.append(f"from .{module} → from {target}")
            return f"from {target} import "
        if dots.startswith(".."):
            target = module or "database"
            changes.append(f"from ..{module} → from {target}")
            return f"from {target} import "
        return m.group(0)

    fixed = _REL_IMPORT_RE.sub(_repl, content)
    return fixed, changes


def ensure_main_py_health_snippet(content: str, api_prefix: str = "/api") -> tuple[str, list[str]]:
    """main.py 缺少 health 时追加标准片段。"""
    prefix = _normalize_prefix(api_prefix)
    if "/health" in content or f'"{prefix}/health"' in content:
        return content, []
    snippet = f'''

@api_router.get("/health")
def studio_health():
    return {{"ok": True}}
'''
    if "api_router" in content and "include_router" in content:
        # insert before include_router
        new = re.sub(
            r"(app\.include_router\s*\(\s*api_router)",
            snippet + r"\n\1",
            content,
            count=1,
        )
        return new, ["已追加 @api_router.get('/health')"]
    snippet_app = f'''

@app.get("{prefix}/health")
def studio_health():
    return {{"ok": True}}
''' if prefix else '''

@app.get("/health")
def studio_health():
    return {"ok": True}
'''
    if "app = FastAPI" in content or "app=FastAPI" in content:
        return content.rstrip() + snippet_app + "\n", ["已追加 health 路由"]
    return content, []


def audit_preview_has_contract(html: str) -> list[str]:
    gaps: list[str] = []
    if MARKER_BEGIN not in html or MARKER_END not in html:
        gaps.append(
            "preview.html 缺少 FULLSTACK_API 标准块；写盘前须 get_fullstack_api_contract，"
            "并由 save_ui_file 自动注入"
        )
    if re.search(r"(?:var|const|let)\s+API\s*=", html, re.I) and MARKER_BEGIN not in html:
        gaps.append("使用了 const API 而非标准 apiGet/apiPost（易与后端基址不一致）")
    if _HARDCODED_PORT_RE.search(html) and MARKER_BEGIN not in html:
        gaps.append("硬编码 127.0.0.1:8xxx，须使用 FULLSTACK_API 标准块中的 API_BASE")
    return gaps


def audit_frontend_studio_compat(
    proj_dir: Path,
    *,
    linked_backend_meta: dict[str, Any] | None = None,
) -> list[str]:
    """前端工程全栈契约兼容性检查。"""
    gaps: list[str] = []
    for rel in ("preview.html", "index.html", "dist/index.html", "public/index.html"):
        fp = proj_dir / rel
        if fp.is_file():
            preview = rel
            break
    else:
        return gaps
    try:
        html = (proj_dir / preview).read_text(encoding="utf-8")
    except OSError:
        return ["preview.html 无法读取"]
    gaps.extend(audit_preview_has_contract(html))
    prefix = "/api"
    if linked_backend_meta:
        prefix = _normalize_prefix(linked_backend_meta.get("api_prefix"))
    if prefix == "/api" and re.search(
        r"(?:fetch|apiGet|apiPost)\s*\(\s*['\"]/api/", html, re.I
    ):
        gaps.append("api_prefix 为 /api 时，请求 path 不要再以 /api/ 开头")
    return gaps


_FETCH_PATH_RE = re.compile(
    r"(?:apiGet|apiPost|apiPut|apiDel)\s*\(\s*[`'](/[^`'\"]+)[`'\"]",
    re.I,
)


def extract_preview_fetch_paths(html: str) -> list[str]:
    paths = []
    for m in _FETCH_PATH_RE.finditer(html):
        p = m.group(1).split("?")[0].strip()
        if p and p not in paths:
            paths.append(p)
    return paths


def _route_suffix(full_path: str, api_prefix: str) -> str:
    """将 /api/employees 转为 apiGet 用的 /employees。"""
    prefix = _normalize_prefix(api_prefix)
    if prefix and full_path.startswith(prefix + "/"):
        return full_path[len(prefix) :]
    if prefix and full_path == prefix:
        return "/"
    return full_path


def audit_fetch_paths_match_backend(
    html: str,
    *,
    backend_proj_dir: Path | None = None,
    linked_backend_meta: dict[str, Any] | None = None,
) -> list[str]:
    """检查 preview 里 apiGet 等路径是否在后端路由表中。"""
    gaps: list[str] = []
    if not backend_proj_dir or not backend_proj_dir.is_dir():
        return gaps
    prefix = _normalize_prefix(
        (linked_backend_meta or {}).get("api_prefix")
    )
    backend_routes = parse_backend_routes(backend_proj_dir)
    if not backend_routes:
        return gaps
    allowed_suffixes: set[str] = set()
    for full in backend_routes:
        suf = _route_suffix(full, prefix)
        allowed_suffixes.add(suf)
        allowed_suffixes.add(full)
    for fetch_path in extract_preview_fetch_paths(html):
        norm = fetch_path if fetch_path.startswith("/") else "/" + fetch_path
        if norm in allowed_suffixes:
            continue
        # 带路径参数的近似匹配：/employees/123 → /employees/{id}
        matched = False
        for full in backend_routes:
            suf = _route_suffix(full, prefix)
            if "{" in full:
                base = re.sub(r"/\{[^}]+\}.*$", "", suf)
                if base and norm.startswith(base + "/"):
                    matched = True
                    break
            if norm.startswith(suf + "/") and suf.endswith("}"):
                matched = True
                break
        if not matched:
            gaps.append(
                f"preview 请求 {norm!r} 不在后端路由表中；"
                f"请 get_fullstack_api_contract 并按 backend_routes 修改"
            )
    return gaps[:8]


def audit_backend_route_contract(proj_dir: Path, meta: dict[str, Any]) -> list[str]:
    """禁止双轨路由（manifest 为 /api 时又注册无前缀业务路由）。"""
    gaps: list[str] = []
    prefix = _normalize_prefix(meta.get("api_prefix"))
    main_py = proj_dir / "main.py"
    if not main_py.is_file():
        return gaps
    try:
        text = main_py.read_text(encoding="utf-8")
    except OSError:
        return gaps
    if prefix == "/api":
        if re.search(r'add_api_route\s*\(\s*["\']/(?!api/)', text):
            gaps.append(
                "main.py 含无前缀 add_api_route 兼容路由；api_prefix=/api 时须删除，"
                "业务路由统一走 APIRouter(prefix=\"/api\")"
            )
        has_root_health = bool(
            re.search(r'@app\.get\s*\(\s*["\']/health["\']', text)
        )
        has_api_router = 'prefix="/api"' in text or "prefix='/api'" in text
        if has_root_health and has_api_router:
            gaps.append(
                'main.py 同时有 @app.get("/health") 与 /api 路由；'
                '仅保留 @api_router.get("/health")'
            )
    return gaps
