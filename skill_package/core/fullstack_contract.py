"""Full-stack API contract: single source of truth for skill-generated code (no Studio runtime patches)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skill_package.workspace.paths import backend_dir, frontend_dir, validate_db_alias

API_MANIFEST = "api_manifest.json"
UI_MANIFEST = "ui_manifest.json"
MARKER_BEGIN = "/* === FULLSTACK_API_BEGIN — maintained by skill tools, do not delete === */"
MARKER_BEGIN_LEGACY = "/* === FULLSTACK_API_BEGIN — 由 skill 工具维护，勿删 === */"
MARKER_END = "/* === FULLSTACK_API_END === */"

_ROUTER_PREFIX_RE = re.compile(
    r'APIRouter\s*\(\s*[^)]*prefix\s*=\s*["\']([^"\']+)["\']',
    re.I,
)
_ROUTE_DECORATOR_RE = re.compile(
    r"@(?:app|[\w_]+)\.(?:get|post|put|delete|patch|head|options)\(\s*[\"']([^\"']*)[\"']",
    re.I,
)
def _has_fullstack_api_block(html: str) -> bool:
    return MARKER_BEGIN in html or MARKER_BEGIN_LEGACY in html


def _fullstack_block_pattern() -> re.Pattern[str]:
    markers = "|".join(re.escape(m) for m in (MARKER_BEGIN, MARKER_BEGIN_LEGACY))
    return re.compile(markers + r"[\s\S]*?" + re.escape(MARKER_END), re.M)


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
    """Resolve the linked frontend ↔ backend pair."""
    alias = validate_db_alias(db_alias)
    backends = _scan_backend_projects(alias)
    frontends = _scan_frontend_projects(alias)
    if not backends:
        raise ValueError(
            f"Workspace {alias} has no DB-connected backend (backend/*/api_manifest.json)"
        )
    if not frontends:
        raise ValueError(
            f"Workspace {alias} has no DB-connected frontend (frontend/*/ui_manifest.json)"
        )

    be_row: dict[str, Any] | None = None
    fe_row: dict[str, Any] | None = None

    if backend_project:
        be_row = next((b for b in backends if b["project_name"] == backend_project), None)
        if not be_row:
            raise ValueError(f"Backend project not found: backend/{backend_project}")
        linked = str(be_row["meta"].get("linked_frontend") or "").strip()
        if linked:
            fe_row = next((f for f in frontends if f["project_name"] == linked), None)
        if not fe_row and frontend_project:
            fe_row = next((f for f in frontends if f["project_name"] == frontend_project), None)
    elif frontend_project:
        fe_row = next((f for f in frontends if f["project_name"] == frontend_project), None)
        if not fe_row:
            raise ValueError(f"Frontend project not found: frontend/{frontend_project}")
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
        raise ValueError(
            "Cannot resolve backend project; set backend_project or api_manifest.linked_frontend"
        )
    if not fe_row:
        raise ValueError(
            f"Backend backend/{be_row['project_name']} linked_frontend does not point to a frontend; "
            "update api_manifest.json via save_backend_file"
        )
    return {"db_alias": alias, "backend": be_row, "frontend": fe_row}


def parse_backend_routes(proj_dir: Path) -> list[str]:
    """Extract public routes from main.py and routers/*.py (including /api prefix)."""
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
    """Build frontend/backend contract (read before writing preview.html or fetch calls)."""
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
            f"api_manifest.linked_frontend={linked!r} does not match frontend {fe['project_name']!r}"
        )
    if not routes:
        gaps.append("No routes parsed from main.py / routers; check @api_router.get decorators")
    if f"{api_prefix}/health" not in routes and "/health" not in routes:
        gaps.append("Missing GET /api/health or GET /health; include health check in main.py")

    rel_imports = find_relative_imports_in_dir(proj_dir)
    if rel_imports:
        gaps.append(f"Backend uses relative imports (use absolute): {', '.join(rel_imports[:3])}")
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
            "API_BASE already includes api_prefix; fetch/apiGet paths must not start with /api."
            if api_prefix
            else "api_prefix is empty; paths start at root (e.g. /employees)."
        ),
        "backend_routes": routes,
        "route_fetch_map": route_fetch_map,
        "preview_api_block": block,
        "preview_must_include_marker": MARKER_BEGIN,
        "gaps": gaps,
        "agent_instructions": [
            "Before preview.html: put preview_api_block in the first <script> (save_ui_file injects it).",
            "Use only apiGet/apiPost/apiPut/apiDel; do not set fetch base URL or const API.",
            f"Example: apiGet('{routes[1] if len(routes) > 1 else '/employees'}') maps to a real backend route.",
            "After backend work: save_api_knowledge; before closing: verify_fullstack_deliverables.",
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
      if (el) {{ el.textContent = 'API connected'; el.className = 'status online'; }}
      return true;
    }}
  }} catch (e) {{}}
  if (el) {{
    el.textContent = 'API not connected (' + API_BASE + ')';
    el.className = 'status';
  }}
  return false;
}}
{MARKER_END}"""


def ensure_preview_api_block(html: str, contract: dict[str, Any]) -> tuple[str, list[str]]:
    """Write the standard API layer into preview.html (replace block or insert in first script)."""
    block = str(contract.get("preview_api_block") or "")
    if not block:
        return html, []
    changes: list[str] = []

    if _has_fullstack_api_block(html) and MARKER_END in html:
        new_html = _fullstack_block_pattern().sub(block, html, count=1)
        if new_html != html:
            changes.append("Updated FULLSTACK_API standard block")
        return new_html, changes

    cleaned = html
    api_old = re.compile(r"(?:var|const|let)\s+API\s*=[^;]+;", re.I | re.M)
    base_old = re.compile(r"(?:var|const|let)\s+API_BASE\s*=[^;]+;", re.I | re.M)
    for pat in (api_old, base_old):
        if pat.search(cleaned) and not _has_fullstack_api_block(cleaned):
            cleaned = pat.sub("", cleaned, count=1)
            changes.append("Removed legacy API/API_BASE declarations (replaced by standard block)")

    if "<script" in cleaned.lower():
        new_html = re.sub(
            r"(<script[^>]*>)",
            r"\1\n" + block + "\n",
            cleaned,
            count=1,
            flags=re.I,
        )
        changes.append("Injected FULLSTACK_API standard block into first <script>")
        return new_html, changes

    insert = f"<script>\n{block}\n</script>\n"
    if "</body>" in cleaned.lower():
        new_html = re.sub(r"</body>", insert + "</body>", cleaned, count=1, flags=re.I)
    else:
        new_html = cleaned + insert
    changes.append("Appended FULLSTACK_API standard block")
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
    """Rewrite common relative imports to absolute (routers / database in same project)."""
    changes: list[str] = []

    def _repl(m: re.Match[str]) -> str:
        dots = m.group(1)
        module = (m.group(2) or "").strip(".")
        if dots == ".":
            target = module or "routers"
            changes.append(f"from .{module} -> from {target}")
            return f"from {target} import "
        if dots.startswith(".."):
            target = module or "database"
            changes.append(f"from ..{module} -> from {target}")
            return f"from {target} import "
        return m.group(0)

    fixed = _REL_IMPORT_RE.sub(_repl, content)
    return fixed, changes


def ensure_main_py_health_snippet(content: str, api_prefix: str = "/api") -> tuple[str, list[str]]:
    """Append standard health route snippet when main.py lacks /health."""
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
        return new, ["Appended @api_router.get('/health')"]
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
        return content.rstrip() + snippet_app + "\n", ["Appended health route"]
    return content, []


def audit_preview_has_contract(html: str) -> list[str]:
    gaps: list[str] = []
    if not _has_fullstack_api_block(html) or MARKER_END not in html:
        gaps.append(
            "preview.html missing FULLSTACK_API block; call get_fullstack_api_contract before save; "
            "save_ui_file should inject it"
        )
    if re.search(r"(?:var|const|let)\s+API\s*=", html, re.I) and not _has_fullstack_api_block(html):
        gaps.append("Uses const API instead of apiGet/apiPost (API base may drift from backend)")
    if _HARDCODED_PORT_RE.search(html) and not _has_fullstack_api_block(html):
        gaps.append("Hardcoded 127.0.0.1:8xxx; use API_BASE from FULLSTACK_API block")
    return gaps


def audit_frontend_studio_compat(
    proj_dir: Path,
    *,
    linked_backend_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Full-stack contract compatibility check for a frontend project."""
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
        return ["Cannot read preview.html"]
    gaps.extend(audit_preview_has_contract(html))
    prefix = "/api"
    if linked_backend_meta:
        prefix = _normalize_prefix(linked_backend_meta.get("api_prefix"))
    if prefix == "/api" and re.search(
        r"(?:fetch|apiGet|apiPost)\s*\(\s*['\"]/api/", html, re.I
    ):
        gaps.append('When api_prefix is /api, request paths must not start with "/api/"')
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
    """Map /api/employees to apiGet path /employees."""
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
    """Check preview apiGet paths against the backend route table."""
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
        # Approximate match for path params: /employees/123 -> /employees/{id}
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
                f"preview request {norm!r} not in backend routes; "
                f"call get_fullstack_api_contract and align with backend_routes"
            )
    return gaps[:8]


def audit_backend_route_contract(proj_dir: Path, meta: dict[str, Any]) -> list[str]:
    """Disallow dual routes (/api manifest plus unprefixed business routes)."""
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
                "main.py has unprefixed add_api_route shim; with api_prefix=/api remove it and "
                'use APIRouter(prefix="/api") for business routes'
            )
        has_root_health = bool(
            re.search(r'@app\.get\s*\(\s*["\']/health["\']', text)
        )
        has_api_router = 'prefix="/api"' in text or "prefix='/api'" in text
        if has_root_health and has_api_router:
            gaps.append(
                'main.py has both @app.get("/health") and /api routes; '
                'keep only @api_router.get("/health")'
            )
    return gaps
