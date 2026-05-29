---
name: UI_build
description: >-
  在 workspace/{db_alias}/ 生成接库前端，并维护 UI 知识文档；
  产出含 frontend 工程与 ui_knowledge.md。用户可在 Skill Studio 预览整页效果。
version: "2.1"
---

## 生成硬性规范（首要：系统能运行）

全栈任务必须先有合规 backend，再写前端。`save_ui_file` 若违反规范会返回 **`blocked: true`**。

1. 优先使用 **`scaffold_fullstack_project`**（backend skill）初始化
2. **`get_fullstack_api_contract`** → 只按 `route_fetch_map` 写 `apiGet('/path')`
3. **`save_ui_file`** 写 `preview.html`（自动注入 FULLSTACK_API 块）
4. **`verify_fullstack_deliverables`** 通过后才能对用户说「系统可用」

**禁止**：`const API`、硬编码 `127.0.0.1:8xxx`、自写 `API_BASE`、path 以 `/api/` 重复前缀。

## 目标

本 skill 负责 **两类产出**（同一 `db_alias` 工作区）：

| 产出 | 路径 | 说明 |
|------|------|------|
| **前端工程** | `frontend/{project_name}/` | 页面代码、资源、`ui_manifest.json` |
| **UI 知识文档** | `frontend/{project_name}/ui_knowledge.md` | 样式、排版、组件、交互等可延续的设计约定 |

与 **database** skill 共用 `config.json`、`dataset/`、`manifest.json`。

## 全栈对接（最重要）

前后端能否联动，取决于生成代码是否遵守 **全栈 API 契约**，而不是 Studio 运行时修补。

### 标准流程

1. **backend skill 先完成** `main.py`、`api_manifest.json`（`linked_frontend` = 本前端目录名）
2. **必调** `get_fullstack_api_contract(db_alias, frontend_project=...)`  
   返回：`api_base_url`、`backend_routes`、`preview_api_block`、`fetch_path_rule`
3. **`save_ui_file` 写 `preview.html`**  
   - 工具会 **自动注入/更新** `FULLSTACK_API` 标准块（含 `apiGet`/`apiPost`/`checkBackendHealth`）  
   - 你只需写业务 UI 和 `apiGet('/路由')` 调用  
   - **禁止**自写 `const API`、`const API_BASE`、硬编码 `127.0.0.1:8000`
4. 业务 `fetch` 路径必须来自 `contract.backend_routes`（`API_BASE` 已含 `/api` 时 path **不要**再以 `/api` 开头）
5. 收尾 **`verify_fullstack_deliverables`**，`system_complete: true` 才能说系统可用

模板：`skill_package/skills/UI_build/assets/_template_preview_studio.html`

### FULLSTACK_API 标准块

`save_ui_file` 保存 HTML 时自动维护如下标记块（勿删）：

```
/* === FULLSTACK_API_BEGIN — 由 skill 工具维护，勿删 === */
const API_BASE = (window.__STUDIO_API_BASE__ || 'http://127.0.0.1:8000/api');
async function apiGet(path) { ... }
/* === FULLSTACK_API_END === */
```

Studio 系统预览会注入 `window.__STUDIO_API_BASE__` 覆盖本地兜底地址。

## 标准流程（SOP）

### 0. 澄清需求

页面类型、技术栈（默认 React+Vite+TS）、**`db_alias`**。表结构优先读 **`dataset/`**。

### 1. 数据库配置（用户提供连接时）

**`save_database_config`** → `config.json`（含 `source_databases` + `target_database`，勿复述 password）。

### 2. 检查已有前端

**`check_db_connected_frontend`** → 存在则 **`read_ui_asset`** 迭代；否则新建 `frontend/{project_name}/`。

### 3. 新建 / 迭代前端工程

1. 写入 **`ui_manifest.json`**（`has_database_connection: true`）
2. **`get_fullstack_api_contract`**（后端已存在时 **必调**）
3. **`save_ui_file`** 整文件落盘；**`patch_ui_file`** 片段替换（小改优先）
4. **必须提供 `preview.html`**，且保存后检查工具返回无 `studio_gaps`
5. **`get_frontend_preview`** 确认 Studio 可预览
6. 全栈任务收尾前 **`verify_fullstack_deliverables`** 须 `system_complete: true`

**禁止**在未调用 `save_ui_file` 的情况下向用户声称 `frontend/` 或 `preview.html` 已存在。

### 4. 整理 UI 知识

更新 **`ui_knowledge.md`**：布局、组件、**与后端的接口约定**（复制 contract 中的路由表）。

### 5. 收尾（必做）

用中文说明：做了什么、产物路径、如何在 Studio 系统预览查看、本地运行方式。

## 工具一览

| 工具 | 作用 |
|------|------|
| **`get_fullstack_api_contract`** | **写 preview 前必调**；前后端路由与 API 基址契约 |
| `check_db_connected_frontend` | 是否已有接库前端 |
| `list_ui_assets` | 列举前端工程 |
| `read_ui_asset` / `save_ui_file` | 读/整文件写（HTML 自动注入 FULLSTACK_API） |
| `patch_ui_file` | 片段替换已有源码 |
| `read_ui_knowledge` / `save_ui_knowledge` | 读/写 UI 知识文档 |
| `get_frontend_preview` | 查询 Studio 预览入口 |
| `verify_fullstack_deliverables` | 全栈交付检查（backend skill 注册） |

## 与 backend skill 协作

- **顺序**：database → **backend** → **get_fullstack_api_contract** → UI_build
- `api_manifest.linked_frontend` = 本前端目录名
- 所有数据请求用 **`apiGet`/`apiPost`**，路径与 `api_knowledge.md` 一致

## 安全

- 密码仅在 `config.json`；前端不存明文密码。
- 新建接库工程须有 `ui_manifest.json` 且 `has_database_connection: true`。

## 编排层

`ensure_tools_loaded("UI_build")`。
