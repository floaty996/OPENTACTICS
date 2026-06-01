---
name: database
description: >-
  Read-only analysis of customer databases; write table structures and data
  relationships to skill_package/workspace/{db_alias}/dataset/. Check existing
  dataset docs first; connect to the database only when insufficient. Shares
  workspace with UI_build.
version: "1.4"
---

## Goal

Build a **reusable business knowledge base** for customer databases, co-located with UI and config under **`workspace/{db_alias}/`** so multiple skills can chain together.

## Source vs target database (required reading)

| Type | Config field | Connection | Agent permissions |
|------|--------------|------------|-------------------|
| **Source DB** | `source_databases` (multiple, **optional**) | `database_connect(connection_mode="source", database="...", use_workspace_config=true)` | **Read-only** (SELECT/SHOW/DESCRIBE…) |
| **Source files** | `source_files` (xlsx/csv, **optional**) | `list_source_files` → `read_source_file(path=...)` | **Read-only** preview; write findings to `dataset/` |
| **Target DB** | `target_database` (single, **optional**) | `database_connect(connection_mode="target", use_workspace_config=true)` | **Writable** (CREATE/INSERT/ALTER…) |
| **Local DB** | `storage_mode: "local"` (when target is empty) | Same `connection_mode="target"` → SQLite `workspace/{db_alias}/data/app.db` | **Writable** (that SQLite file only) |

- **Document sources**: connect each **source DB** or read **source_files**; no DDL/DML on sources. If no sources, skip DB connect and write `dataset/` or use local SQLite.
- **Create tables / persist data**: connect **target DB** (MySQL) or **local SQLite** (`connection_mode=target`).
- Before writes, call `read_database_config` to confirm `storage_mode` / `target_database`.
- **`password: "***"` in `read_database_config` is redacted**; never pass `***` to `save_database_config`. Change passwords in Studio init or pass real passwords via `save_database_config`.

## Workspace layout (shared with UI_build)

```
skill_package/workspace/{db_alias}/
├── config.json       # source_databases + source_files + target_database (all optional) + storage_mode
├── dataset/          # This skill writes Markdown knowledge docs here
├── source_files/     # Studio-uploaded xlsx/csv (read-only)
├── frontend/         # UI_build writes here
└── manifest.json     # Artifact index
```

- Knowledge docs: `workspace/{db_alias}/dataset/{YYYYMMDD}_{topic}.md`
- Template: `skill_package/workspace/_templates/dataset_knowledge.md`

### Path snapshot (auto-updated on load)

```run-python
from pathlib import Path
import json

ws = (Path.cwd().parent.parent / "workspace").resolve()
print("[Tool parameters]")
print("  save_markdown / read_database_knowledge:")
print("    db_alias=customer alias")
print("    file_path=relative to dataset/, e.g. 20260521_order_domain.md")
print("  list_database_knowledge: db_alias optional (scans all workspaces)")
print()
if not ws.is_dir():
    print("(No workspace directory yet)")
else:
    for alias_dir in sorted(ws.iterdir()):
        if not alias_dir.is_dir() or alias_dir.name.startswith("_"):
            continue
        ds = alias_dir / "dataset"
        if not ds.is_dir():
            continue
        mds = sorted(ds.rglob("*.md"))
        if not mds:
            continue
        print(f"[{alias_dir.name}]")
        for p in mds:
            if p.name.startswith("_"):
                continue
            print(f"  - dataset/{p.relative_to(ds).as_posix()}")
        mp = alias_dir / "manifest.json"
        if mp.is_file():
            try:
                man = json.loads(mp.read_text(encoding="utf-8"))
                print(f"  manifest.projects: {len(man.get('projects') or [])} frontend project(s)")
            except Exception:
                pass
```

## Standard workflow (SOP)

### 0. Clarify business requirements

Understand goals, scope, and focus areas; put `business_goal` / `scope` in document YAML frontmatter.

### 1. Check dataset first (required)

1. **`list_database_knowledge`** (pass `db_alias` when possible)
2. **`read_database_knowledge`** (`db_alias` + `file_name`)
3. If insufficient or refresh needed → step 2

Optional: **`read_workspace_manifest`** (UI_build tool) to see existing config/frontend in the workspace.

### 2. Connect to customer database

**`database_connect`** (prefer `use_workspace_config=true`):

| Scenario | Parameters |
|----------|------------|
| Document source DB A | `connection_mode="source"`, `database="source_db_name"` |
| Create tables / write | `connection_mode="target"` (DB name from `target_database`) |

**Never echo passwords in replies**; always **`database_disconnect`** when done.

### 3. Read-only exploration

`list_tables` → `describe_table` → `database_query` (read-only SQL); sample rows must be redacted.

### 4. Write to dataset

**`save_markdown`** for full files; prefer **`patch_markdown`** (`old_string` / `new_string`) for small edits → update `manifest.json` `knowledge_files`.

### 5. Wrap-up

Report workspace paths, whether existing docs were reused, uncovered tables, and open questions.

If the user wants a **full business system** (not just docs), after dataset hand off to:

1. **backend** skill: `save_backend_file` for API (including `main.py`)
2. **UI_build** skill: `save_ui_file` for `frontend/` and `preview.html`
3. Before closing: **`verify_fullstack_deliverables`** (backend tool)

**Do not** claim frontend/full-stack is done after dataset only.

## Tools

| Tool | Purpose |
|------|---------|
| `list_database_knowledge` | List md files under dataset (optional db_alias) |
| `read_database_knowledge` | Read md |
| `save_markdown` | Save full md file |
| `patch_markdown` | Patch existing md |
| `database_connect` / `database_disconnect` | Connect / disconnect |
| `list_tables` / `describe_table` / `database_query` | Read-only exploration |
| `list_source_files` / `read_source_file` | Workspace xlsx/csv sources |

## Dependencies

MySQL: `pymysql`; PostgreSQL: `psycopg2-binary`; SQLite: built-in.

## Orchestration

Call `ensure_tools_loaded("database")`. Use the same **`db_alias`** as **UI_build** when collaborating.
