---
name: backend
description: >-
  Generate DB-connected REST APIs under workspace/{db_alias}/backend/ (default FastAPI)
  and maintain api_knowledge.md. Shares workspace with database and UI_build; supplies real data APIs for the frontend.
version: "1.4"
studio_visible: true
---

## Hard generation rules (priority: system must run)

**Read before new full-stack work**: call `get_fullstack_generation_spec`.

| Phase | Tool | Requirement |
|-------|------|-------------|
| Init | **`scaffold_fullstack_project`** | One-shot compliant backend + frontend skeleton |
| Backend | `save_backend_file` | Violations **block write** (`blocked: true`) |
| Contract | `get_fullstack_api_contract` | Routes per `route_fetch_map` |
| Frontend | UI_build `save_ui_file` | No `const API`, no hardcoded ports |
| Close | `verify_fullstack_deliverables` | **`system_complete: true`** before claiming the system works |

**Forbidden**: unprefixed `add_api_route` shims, `from .` relative imports, `api_prefix` other than `"/api"` or `""`.

## Goal

This skill owns **backend API projects** and **API knowledge docs**, paired with **UI_build** frontends:

| Output | Path | Notes |
|--------|------|-------|
| **Backend project** | `backend/{project_name}/` | FastAPI routes, data access, `requirements.txt` |
| **API knowledge** | `backend/{project_name}/api_knowledge.md` | Routes, request/response, table mapping, frontend integration |

Shares `config.json`, `dataset/`, `manifest.json` with **database** and **UI_build**.

## Workspace layout

```
skill_package/workspace/{db_alias}/
├── config.json
├── dataset/                    # database skill
├── frontend/{name}/            # UI_build skill
├── backend/{name}/             # this skill
│   ├── api_manifest.json
│   ├── api_knowledge.md
│   ├── main.py
│   ├── requirements.txt
│   └── routers/ …
└── manifest.json
```

Templates:

- `skill_package/workspace/_templates/api_manifest.json`
- `skill_package/workspace/_templates/api_knowledge.md`
- `skill_package/skills/backend/assets/_template_main_studio.py` (single-file entry)
- `skill_package/skills/backend/assets/_template_routers_layout.md` (**multi-file routers/, required reading**)

## Standard workflow (SOP)

### 0. Clarify requirements

Business scenario, APIs to expose, **`db_alias`**. Read table structures from **`dataset/`** first; if a **UI_build** frontend exists, read `frontend/{name}/ui_knowledge.md` and keep **`linked_frontend`** aligned.

### 1. Check existing backend

**`check_db_connected_backend`** → if exists, **`read_backend_file`** and iterate; else create under `backend/` (**name should match frontend or use `-api` suffix**).

### 2. Create / iterate backend

1. Write **`api_manifest.json`** (`has_database_connection: true`, `linked_frontend` = frontend dir, **`api_prefix` = `"/api"`**)
2. **`save_backend_file`** for full writes; **`patch_backend_file`** for small edits
3. **Imports (hard rule)**: Studio runs `uvicorn main:app`; **all** `.py` use **absolute imports** (see §4.2). **No** `from .routers`, `from ..database`, etc.
4. **Routes (hard rule)**: `main.py` uses `api_router = APIRouter(prefix="/api")` and `app.include_router(api_router)`; include **`GET /api/health`** (`save_backend_file` can auto-add)
5. With `routers/`: add `routers/__init__.py` and `from routers import xxx` in `main.py`
6. Use **database** skill `database_connect` + `database_query` for real queries
7. **CORS** for `http://127.0.0.1:8765` and `http://localhost:8765`
8. **`get_backend_run_info`**: `studio_gaps` must be empty
9. **`get_fullstack_api_contract`** → hand off to UI_build

### 3. API knowledge (required)

1. **`read_api_knowledge`** if present
2. Update **`api_knowledge.md`**: routes, params, responses, errors, mapping to `dataset` tables
3. **`save_api_knowledge`**

### 4. Frontend alignment (this skill does not write frontend)

- Set **`linked_frontend`** in `api_manifest.json`
- **Do not** describe `frontend/` pages/components unless **UI_build** wrote them via `save_ui_file`
- After backend, if user wants a “system/page”, hand off: **continue with UI_build for frontend**
- `preview.html` `API_BASE` / fetch paths must match **real main.py routes**
- **`api_prefix` in manifest must match main.py**; if `"/api"`, routes must be under `/api/`; if `""`, do not double-prefix in preview
- Before closing: **`verify_fullstack_deliverables`**, **`studio_gaps` empty** before claiming Studio preview works

### 4.2 Skill Studio preview rules (required)

When user clicks **Restart** in **Skill Studio → System preview**, `studio/backend_runner.py` starts the backend (**no `--reload`**, no code fixes). Generated backends **must** follow these rules.

#### How Studio starts the backend

| Item | Rule |
|------|------|
| Working dir | `workspace/{db_alias}/backend/{project_name}/` |
| Command | `python -m uvicorn main:app --host 127.0.0.1 --port {default_port}` |
| Entry | `main.py` must define **`app = FastAPI(...)`** and import cleanly |
| Deps | First start runs `pip install -r requirements.txt` (~180s max); wait before retrying restart |
| Port | `api_manifest.json` → `default_port` (default 8000); next port if busy |

#### `api_manifest.json` fields

```json
{
  "linked_frontend": "same name as frontend/ directory",
  "default_port": 8000,
  "api_prefix": "/api"
}
```

- **`api_prefix`**: only **`"/api"`** or **`""`** — no prose (bad: `"/api (also no prefix)"` breaks URL probing)
- **`linked_frontend`**: **required**
- **`default_port`**: integer, recommend 8000

#### `main.py` and multi-file projects

Studio runs **`uvicorn main:app`** with cwd `backend/{project}/`. `main.py` is a **top-level script**, not a package module:

| Rule | Detail |
|------|--------|
| **No relative imports** | No `from .xxx` or `from ..xxx` anywhere |
| **Absolute imports** | `from routers import employees`, `from database import get_connection` |
| **routers package** | `routers/__init__.py` required (may be empty) |

See `_template_routers_layout.md` and `_template_main_studio.py`.

**Recommended**: single `/api` prefix matching manifest.

For **dual paths** (no prefix + `/api`): define `direct_router = APIRouter()` first, register it, keep manifest `api_prefix: "/api"`.

#### Environment variables (Studio injects; database.py should read first)

| Variable | Meaning |
|----------|---------|
| `STUDIO_WORKSPACE_CONFIG` | Absolute path to `workspace/{db_alias}/config.json` |
| `STUDIO_DB_ALIAS` | Current `db_alias` |
| `STUDIO_STORAGE_MODE` | `local` or `mysql` |
| `STUDIO_LOCAL_SQLITE` | SQLite path in local mode |
| `DB_PASSWORD` / `DB_TARGET_PASSWORD` | Source/target passwords from config |

When `storage_mode=local`, do **not** hardcode MySQL; use `STUDIO_LOCAL_SQLITE` or `database_connect(..., use_workspace_config=true)`.

#### CORS

Allow at least `http://127.0.0.1:8765` and `http://localhost:8765` (add `5173` for Vite dev).

#### Health / probing

Studio probes `/api/health`, `/health`, `/openapi.json`, etc. Provide **`GET /api/health`**.

#### Post-write checks

1. **`get_backend_run_info`**: `ready_for_studio` true, `studio_gaps` empty
2. **`verify_fullstack_deliverables`**: `system_complete` true before claiming full-stack preview

### 4.1 Minimum backend deliverables

New DB-connected backend **must** include:

| File | Purpose |
|------|---------|
| `main.py` | uvicorn entry |
| `api_manifest.json` | `has_database_connection`, `linked_frontend` |
| `requirements.txt` | Dependencies |
| `api_knowledge.md` | Routes and integration (recommended same batch) |

Without `main.py`, **do not** claim the backend can start.

### 5. Wrap-up (required user-facing reply)

After tools finish, **explain clearly to the user**, including:

1. Which backend files were created/changed
2. Path `workspace/{db_alias}/backend/{project}/`
3. **How to run**: local `get_backend_run_info.run_commands`; Studio preview uses `studio_run_command` (no `--reload`)
4. **Frontend integration**: API base URL, main endpoints
5. Whether `api_knowledge.md` was updated
6. If same session as UI_build: **`verify_fullstack_deliverables`** with `system_complete: true` before claiming full-stack done

## Recommended stack

- **Framework**: FastAPI + Uvicorn
- **Config**: `workspace/{db_alias}/config.json` (same as database skill); local mode → SQLite via `STUDIO_LOCAL_SQLITE` or `database_connect(connection_mode=target, use_workspace_config=true)`
- **API prefix**: default `/api`
- **Port**: default `8000` in `api_manifest.json`

## Tools

| Tool | Purpose |
|------|---------|
| **`scaffold_fullstack_project`** | **Preferred for new full-stack**; scaffold + write |
| **`get_fullstack_generation_spec`** | Full hard rules |
| **`get_fullstack_api_contract`** | Required before preview; `route_fetch_map` |
| `list_backend_projects` | List backend projects |
| `check_db_connected_backend` | Existing DB-connected backend? |
| `read_backend_file` / `save_backend_file` | Read / full write (auto-fix relative imports, health) |
| `patch_backend_file` | Fragment replace |
| `read_api_knowledge` / `save_api_knowledge` | API knowledge docs |
| `get_backend_run_info` | Run commands, port, **Studio checks** (`studio_gaps`) |
| `verify_fullstack_deliverables` | Read-only full-stack audit before close |

## Collaboration

| Skill | Role |
|-------|------|
| **database** | `dataset/*.md`; `database_connect` / `database_query` |
| **UI_build** | `frontend/` and `ui_knowledge.md` |
| **backend** (this) | `backend/` REST API and `api_knowledge.md` |

Typical order: `database` → **`backend` API** → **`get_fullstack_api_contract`** → `UI_build` writes `preview.html`.

## Security

- Passwords only in `config.json`; no plaintext in backend code
- Source DB: SELECT only; DDL/DML on target only
- New DB-connected projects need `api_manifest.json` with `has_database_connection: true`

## Orchestration

Call `ensure_tools_loaded("backend")`.
