---
name: UI_build
description: >-
  Generate DB-connected frontends under workspace/{db_alias}/ and maintain UI knowledge docs;
  outputs frontend projects and ui_knowledge.md. Previewable in Skill Studio.
version: "2.1"
---

## Hard generation rules (priority: system must run)

Full-stack work needs a compliant backend before frontend. `save_ui_file` returns **`blocked: true`** on violations.

1. Prefer **`scaffold_fullstack_project`** (backend skill) to initialize
2. **`get_fullstack_api_contract`** → use only `route_fetch_map` paths in `apiGet('/path')`
3. **`save_ui_file`** for `preview.html` (auto-injects FULLSTACK_API block)
4. **`verify_fullstack_deliverables`** must pass before telling the user the system works

**Forbidden**: `const API`, hardcoded `127.0.0.1:8xxx`, custom `API_BASE`, paths starting with `/api/` when `API_BASE` already includes `/api`.

## Goal

Two outputs in the same **`db_alias`** workspace:

| Output | Path | Notes |
|--------|------|-------|
| **Frontend project** | `frontend/{project_name}/` | Pages, assets, `ui_manifest.json` |
| **UI knowledge** | `frontend/{project_name}/ui_knowledge.md` | Layout, components, interaction conventions |

Shares `config.json`, `dataset/`, `manifest.json` with **database** skill.

## Full-stack integration (most important)

Frontend/backend linkage depends on obeying the **full-stack API contract**, not Studio runtime patches.

### Standard flow

1. **backend skill** completes `main.py`, `api_manifest.json` (`linked_frontend` = this frontend dir)
2. **Required**: `get_fullstack_api_contract(db_alias, frontend_project=...)`
   Returns: `api_base_url`, `backend_routes`, `preview_api_block`, `fetch_path_rule`
3. **`save_ui_file` for `preview.html`**
   - Tool **auto-injects/updates** FULLSTACK_API block (`apiGet`/`apiPost`/`checkBackendHealth`)
   - You write business UI and `apiGet('/route')` only
   - **No** custom `const API`, `const API_BASE`, or hardcoded `127.0.0.1:8000`
4. Fetch paths from `contract.backend_routes` (when `API_BASE` includes `/api`, path **must not** start with `/api/`)
5. Close with **`verify_fullstack_deliverables`**, `system_complete: true`

Template: `skill_package/skills/UI_build/assets/_template_preview_studio.html`

### FULLSTACK_API block

`save_ui_file` maintains this marker block (do not delete):

```
/* === FULLSTACK_API_BEGIN — maintained by skill tools, do not delete === */
const API_BASE = (window.__STUDIO_API_BASE__ || 'http://127.0.0.1:8000/api');
async function apiGet(path) { ... }
/* === FULLSTACK_API_END === */
```

Studio preview injects `window.__STUDIO_API_BASE__` over the local fallback.

## Standard workflow (SOP)

### 0. Clarify requirements

Page type, stack (default React+Vite+TS), **`db_alias`**. Read **`dataset/`** for schema.

### 1. Database config (when user provides connection)

**`save_database_config`** → `config.json` (`source_databases` + `target_database`; never echo password).

### 2. Check existing frontend

**`check_db_connected_frontend`** → iterate with **`read_ui_asset`** or create `frontend/{project_name}/`.

### 3. Create / iterate frontend

1. Write **`ui_manifest.json`** (`has_database_connection: true`)
2. **`get_fullstack_api_contract`** (**required** when backend exists)
3. **`save_ui_file`** full write; **`patch_ui_file`** for small edits
4. **Must provide `preview.html`**; verify no `studio_gaps` in tool response
5. **`get_frontend_preview`** confirms Studio entry
6. Before full-stack close: **`verify_fullstack_deliverables`** with `system_complete: true`

**Do not** claim `frontend/` or `preview.html` exist without calling `save_ui_file`.

### 4. UI knowledge

Update **`ui_knowledge.md`**: layout, components, **backend API contract** (copy routes from contract).

### 5. Wrap-up

Explain clearly: what was done, artifact paths, how to open Studio system preview, local run options.

## Tools

| Tool | Purpose |
|------|---------|
| **`get_fullstack_api_contract`** | **Required before preview**; routes and API base |
| `check_db_connected_frontend` | Existing DB-connected frontend? |
| `list_ui_assets` | List frontend projects |
| `read_ui_asset` / `save_ui_file` | Read / write (HTML auto-injects FULLSTACK_API) |
| `patch_ui_file` | Fragment replace |
| `read_ui_knowledge` / `save_ui_knowledge` | UI knowledge docs |
| `get_frontend_preview` | Studio preview entry path |
| `verify_fullstack_deliverables` | Full-stack audit (registered by backend skill) |
| `save_database_config` / `read_database_config` | Workspace DB config |

## Collaboration with backend

- **Order**: database → **backend** → **get_fullstack_api_contract** → UI_build
- `api_manifest.linked_frontend` = this frontend directory name
- All data calls via **`apiGet`/`apiPost`**, paths aligned with `api_knowledge.md`

## Security

- Passwords only in `config.json`; never in frontend code
- New DB-connected projects need `ui_manifest.json` with `has_database_connection: true`

## Orchestration

Call `ensure_tools_loaded("UI_build")`.
