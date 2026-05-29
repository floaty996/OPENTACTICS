---
name: backend
description: >-
  在 workspace/{db_alias}/backend/ 生成接库 REST API（默认 FastAPI），
  并维护 api_knowledge.md。与 database、UI_build 共用同一工作区，为前端提供真实数据接口。
version: "1.4"
studio_visible: true
---

## 生成硬性规范（首要：系统能运行）

**新建全栈系统前必读**：调用 `get_fullstack_generation_spec`。

| 阶段 | 工具 | 要求 |
|------|------|------|
| 初始化 | **`scaffold_fullstack_project`** | 一键生成符合规范的 backend + frontend 骨架 |
| 后端 | `save_backend_file` | 违反规范会 **拒绝写入**（`blocked: true`） |
| 契约 | `get_fullstack_api_contract` | 按 `route_fetch_map` 写路由 |
| 前端 | UI_build `save_ui_file` | 禁止 `const API`、硬编码端口 |
| 收尾 | `verify_fullstack_deliverables` | **`system_complete: true`** 才能说系统可用 |

**禁止**：`add_api_route` 无前缀兼容、`from .` 相对导入、`api_prefix` 非 `"/api"`。

## 目标

本 skill 负责 **后端 API 工程** 与 **API 知识文档**，与 **UI_build** 的前端成对出现：

| 产出 | 路径 | 说明 |
|------|------|------|
| **后端工程** | `backend/{project_name}/` | FastAPI 路由、数据访问、`requirements.txt` |
| **API 知识文档** | `backend/{project_name}/api_knowledge.md` | 路由表、请求/响应、与表映射、前端对接说明 |

与 **database**、**UI_build** 共用 `config.json`、`dataset/`、`manifest.json`。

## 工作区结构

```
skill_package/workspace/{db_alias}/
├── config.json
├── dataset/                    # database skill
├── frontend/{name}/            # UI_build skill
├── backend/{name}/             # 本 skill
│   ├── api_manifest.json
│   ├── api_knowledge.md
│   ├── main.py
│   ├── requirements.txt
│   └── routers/ …
└── manifest.json               # projects + backend_projects
```

模板：

- `skill_package/workspace/_templates/api_manifest.json`
- `skill_package/workspace/_templates/api_knowledge.md`
- `skill_package/skills/backend/assets/_template_main_studio.py`（单文件入口）
- `skill_package/skills/backend/assets/_template_routers_layout.md`（**多文件 routers/ 工程，必读**）

## 标准流程（SOP）

### 0. 澄清需求

明确业务场景、需暴露的接口、**`db_alias`**。表结构优先读 **`dataset/`**；若已有 **UI_build** 前端，读取 `frontend/{name}/ui_knowledge.md` 中的接口约定，并保持 **`linked_frontend`** 一致。

### 1. 检查已有后端

**`check_db_connected_backend`** → 存在则 **`read_backend_file`** 迭代；否则在 `backend/` 下新建工程（**工程名建议与前端同名或加 `-api` 后缀**）。

### 2. 新建 / 迭代后端工程

1. 写入 **`api_manifest.json`**（`has_database_connection: true`，`linked_frontend` 指向前端目录名，**`api_prefix` 固定 `"/api"`**）
2. **`save_backend_file`** 整文件落盘（新建或大改）；**`patch_backend_file`** 按片段替换（小改优先，更快）
3. **导入规范（硬性）**：Studio 用 `uvicorn main:app` 启动，工程内**所有** `.py` 必须用**绝对导入**（见 §4.2）。**禁止** `from .routers`、`from ..database` 等相对导入——`save_backend_file` 会尝试自动修正，但生成时就不要写相对导入。
4. **路由规范（硬性）**：`main.py` 使用 `api_router = APIRouter(prefix="/api")` 并 `app.include_router(api_router)`；须含 **`GET /api/health`**（`save_backend_file` 可自动补全）
5. 若使用 `routers/` 子目录：须创建 `routers/__init__.py`（可为空），并在 `main.py` 写 `from routers import xxx`
6. 使用 **database** skill 的 `database_connect` + `database_query` 实现真实查询
7. 配置 **CORS**，允许 `http://127.0.0.1:8765` 与 `http://localhost:8765`
8. **`get_backend_run_info`** 确认 `studio_gaps` 为空
9. **`get_fullstack_api_contract`** 输出 `backend_routes` 供 UI_build 对接；通知继续 UI_build

### 3. 整理 API 知识（必做）

1. **`read_api_knowledge`**（若存在）
2. 更新 **`api_knowledge.md`**：路由表、参数、响应字段、错误码、与 `dataset` 表字段对应关系
3. **`save_api_knowledge`**

### 4. 与前端对齐（本 skill 不写前端）

- 在 `api_manifest.json` 填写 **`linked_frontend`**
- **禁止**在回复中描述 `frontend/` 下的页面、路由、React 组件——除非 **UI_build** 已用 `save_ui_file` 写入
- 后端完成后，若用户要「系统/页面」，须明确交接：**请继续用 UI_build 创建 frontend**
- 通知用户：前端 `preview.html` 中 `API_BASE` 与 `fetch` 路径须与 **main.py 真实路由** 一致（Studio 会探测，但生成时应自洽）
- **`api_manifest.json` 的 `api_prefix` 必须与 main.py 一致**：若写 `"/api"`，须 `app.include_router(..., prefix="/api")` 或路由以 `/api/` 开头；否则 manifest 填 `""`，且 preview 里请求路径不要重复加 `/api`
- 收尾前调用 **`verify_fullstack_deliverables`**，其中 **`studio_gaps` 为空** 才能说「可在 Studio 系统预览启动」

### 4.2 Skill Studio 系统预览规范（必读）

用户在 **Skill Studio → 系统预览** 点「重启系统」时，由 `studio/backend_runner.py` 自动拉起后端，**不会**使用 `--reload`，也不会替你改代码。生成的后端 **必须** 满足下列约定，否则会出现长时间扫描端口或启动失败。

#### 启动方式（Studio 实际行为）

| 项 | 约定 |
|----|------|
| 工作目录 | `workspace/{db_alias}/backend/{project_name}/` |
| 命令 | `python -m uvicorn main:app --host 127.0.0.1 --port {default_port}` |
| 入口 | `main.py` 内须有 **`app = FastAPI(...)`**，且可被 import（无 NameError / 语法错误） |
| 依赖 | 首次启动自动 `pip install -r requirements.txt`（最长约 180s）；**首次预览请耐心等待**，勿连续狂点重启 |
| 端口 | `api_manifest.json` → `default_port`（默认 8000）；占用时会尝试后续端口 |

#### `api_manifest.json` 字段（机器可读）

```json
{
  "has_database_connection": true,
  "linked_frontend": "与 frontend/ 下目录名一致",
  "default_port": 8000,
  "api_prefix": "/api"
}
```

- **`api_prefix`**：只能是 **`"/api"`** 或 **`""`**，**禁止**写说明文字（反例：`"/api（同时支持无前缀）"` 会导致 Studio 拼错探测 URL）。
- **`linked_frontend`**：**必填**；Studio 按前端工程关联该后端。
- **`default_port`**：整数，建议 8000。

#### `main.py` 与多文件工程（硬性规范）

**Studio 以 `uvicorn main:app` 启动**（工作目录为 `backend/{project}/`）。此时 `main.py` 是**顶层脚本**，不是包内模块，因此：

| 规则 | 说明 |
|------|------|
| **禁止相对导入** | 全工程任何 `.py` 不得出现 `from .xxx` 或 `from ..xxx` |
| **须用绝对导入** | `from routers import employees`、`from database import get_connection` |
| **routers 包** | 使用 `routers/` 时须有 `routers/__init__.py`（可为空） |

**错误（会导致 `ImportError: attempted relative import`）：**

```python
# main.py
from .routers import stations, employees

# routers/stations.py
from ..database import get_connection
```

**正确：**

```python
# main.py
from routers import employees, stations

# routers/stations.py
from database import get_connection
```

完整多文件示例见：`skill_package/skills/backend/assets/_template_routers_layout.md`。  
单文件入口见：`skill_package/skills/backend/assets/_template_main_studio.py`。

**推荐**：路由统一加 `/api` 前缀（与 manifest `api_prefix: "/api"` 一致）：

```python
from routers import employees

app = FastAPI(...)
app.include_router(employees.router)
```

若业务需要 **无前缀 + `/api` 双路径**：

1. **必须**先定义 `direct_router = APIRouter()`，再写 `@direct_router.get(...)`  
2. **禁止**只写装饰器不定义变量（会导致 `NameError`，Studio 启动即失败）  
3. manifest 仍填 `api_prefix: "/api"`（Studio 探测以此前缀为准）

#### 环境变量（Studio 已注入，database.py 应优先读取）

| 变量 | 含义 |
|------|------|
| `STUDIO_WORKSPACE_CONFIG` | `workspace/{db_alias}/config.json` 绝对路径 |
| `STUDIO_DB_ALIAS` | 当前 `db_alias` |
| `STUDIO_STORAGE_MODE` | `local` 或 `mysql` |
| `STUDIO_LOCAL_SQLITE` | local 模式下 SQLite 文件路径 |
| `DB_PASSWORD` / `DB_TARGET_PASSWORD` | 源库/目标库密码（若 config 中有） |

`storage_mode=local` 时 **不要**硬编码 MySQL；应读 `STUDIO_LOCAL_SQLITE` 或 `database_connect(..., use_workspace_config=true)`。

#### CORS

须允许 Studio 来源，至少包含：

- `http://127.0.0.1:8765`
- `http://localhost:8765`

（本地 Vite 开发可加 `5173`。）

#### 健康检查与 API 探测

Studio 会尝试：`/statistics/overview`、`/api/health`、`/health`、`/employees`、`/openapi.json` 等。建议提供 **`GET /api/health`**（或 manifest `api_prefix` 下的 health）。

#### 写盘后自检（必做）

1. **`get_backend_run_info`**：确认 `ready_for_studio` 为 true、`studio_gaps` 为空  
2. **`verify_fullstack_deliverables`**：`system_complete` 为 true 才能声称全栈可在 Studio 预览

### 4.1 后端最低交付物

新建接库后端时 **必须** 落盘至少：

| 文件 | 说明 |
|------|------|
| `main.py` | uvicorn 入口（`uvicorn main:app`） |
| `api_manifest.json` | 含 `has_database_connection`、`linked_frontend` |
| `requirements.txt` | 依赖 |
| `api_knowledge.md` | 路由与对接说明（推荐与后端同批写入） |

缺少 `main.py` 时 **不得** 声称后端可启动。

### 5. 收尾（必做，面向用户回复）

工具调用结束后 **必须用中文说明**，至少包含：

1. 新建/修改了哪些后端文件  
2. 产物路径 `workspace/{db_alias}/backend/{saas名}/`  
3. **如何启动**：本地开发可用 `get_backend_run_info` 的 `run_commands`；**Studio 系统预览**使用其中的 `studio_run_command`（无 `--reload`）  
4. **前端如何接**：API 基址、主要接口列表  
5. 是否已更新 `api_knowledge.md`
6. 若与 UI_build 同会话：是否已调用 **`verify_fullstack_deliverables`**（`system_complete` 为 true 才能说全栈完成）

## 推荐技术约定

- **框架**：FastAPI + Uvicorn  
- **配置**：从 `workspace/{db_alias}/config.json` 读取连接（与 database skill 一致）。`storage_mode=local` 时目标库为 SQLite，优先用环境变量 `STUDIO_LOCAL_SQLITE`（Studio 预览/backend_runner 已注入），或 `database_connect(connection_mode=target, use_workspace_config=true)`  
- **API 前缀**：默认 `/api`  
- **端口**：默认 `8000`（写入 `api_manifest.json` 的 `default_port`）

## 工具一览

| 工具 | 作用 |
|------|------|
| **`scaffold_fullstack_project`** | **新建全栈首选**；生成可启动骨架并落盘 |
| **`get_fullstack_generation_spec`** | 硬性规范全文 |
| **`get_fullstack_api_contract`** | 写 preview 前必调；`route_fetch_map` |
| `list_backend_projects` | 列举后端工程 |
| `check_db_connected_backend` | 是否已有接库后端 |
| `read_backend_file` / `save_backend_file` | 读/整文件写（`.py` 自动修正相对导入、补 health） |
| `patch_backend_file` | 片段替换（`old_string` → `new_string`） |
| `read_api_knowledge` / `save_api_knowledge` | 读/写 API 知识文档 |
| `get_backend_run_info` | 运行命令、端口、**Studio 兼容检查**（`studio_gaps`） |
| `verify_fullstack_deliverables` | 只读检查全栈是否齐全（收尾前必调） |

## 与 database / UI_build 协作

| Skill | 职责 |
|-------|------|
| **database** | `dataset/*.md` 表结构；`database_connect` / `database_query` |
| **UI_build** | `frontend/` 页面与 `ui_knowledge.md` |
| **backend**（本 skill） | `backend/` REST API 与 `api_knowledge.md` |

典型顺序：`database` 梳理表 → **`backend` 提供 API** → **`get_fullstack_api_contract`** → `UI_build` 写 `preview.html`（自动注入 FULLSTACK_API 块）。

## 安全

- 密码仅存 `config.json`；后端代码不提交明文密码  
- 对源库仅 SELECT；DDL/DML 仅目标库  
- 新建接库工程须有 `api_manifest.json` 且 `has_database_connection: true`

## 编排层

`ensure_tools_loaded("backend")`。
