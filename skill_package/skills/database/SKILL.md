---
name: database
description: >-
  连接客户数据库只读分析，将表结构与数据关系写入 skill_package/workspace/{db_alias}/dataset/。
  先查 dataset 已有文档，不足再连库。与 UI_build 共用同一 workspace。
version: "1.4"
---

## 目标

为客户数据库建立**可复用的业务知识库**，并与 UI、配置等同处 **`workspace/{db_alias}/`**，便于多 skill 衔接。

## 源库 vs 目标库（必读）

| 类型 | config 字段 | 连接方式 | 智能体权限 |
|------|-------------|----------|------------|
| **源库** | `source_databases`（可多个，**可留空**） | `database_connect(connection_mode="source", database="某源库", use_workspace_config=true)` | **只读**（SELECT/SHOW/DESCRIBE…） |
| **源文件** | `source_files`（xlsx/csv，**可留空**） | `list_source_files` → `read_source_file(path=...)` | **只读**预览；整理后写入 `dataset/` |
| **目标库** | `target_database`（唯一，**可留空**） | `database_connect(connection_mode="target", use_workspace_config=true)` | **可写**（CREATE/INSERT/ALTER…） |
| **本地库** | `storage_mode: "local"`（未填目标库时自动） | 同上 `connection_mode="target"` → SQLite `workspace/{db_alias}/data/app.db` | **可写**（仅限该 SQLite 文件） |

- 整理资料：逐个连接各**源库**或读取 **source_files**，禁止对源库 DDL/DML；无源库/源文件时可跳过连库，直接写 dataset 或接本地 SQLite。
- 建表/落库：连接 **目标库**（MySQL）或 **本地 SQLite**（`connection_mode=target`）。
- 写操作前须 `read_database_config` 确认 `storage_mode` / `target_database`。
- **`read_database_config` 返回的 `password: "***"` 仅为脱敏**；禁止把 `***` 传给 `save_database_config`。改密码须在 Studio 初始化页操作，或 `save_database_config` 传入真实密码。

## 工作区结构（与 UI_build 共享）

```
skill_package/workspace/{db_alias}/
├── config.json       # source_databases + source_files + target_database（均可空）+ storage_mode + 账号
├── dataset/          # 本 skill 写入：Markdown 知识文档
├── source_files/     # Studio 上传的 xlsx/csv 源数据（只读）
├── frontend/         # UI_build 写入
└── manifest.json     # 产物索引
```

- 知识文档：`workspace/{db_alias}/dataset/{YYYYMMDD}_{主题}.md`
- 模板：`skill_package/workspace/_templates/dataset_knowledge.md`

### 路径快照（加载时自动更新）

```run-python
from pathlib import Path
import json

ws = (Path.cwd().parent.parent / "workspace").resolve()
print("【工具参数】")
print("  save_markdown / read_database_knowledge:")
print("    db_alias=客户别名")
print("    file_path=相对 dataset/，如 20260521_order_domain.md")
print("  list_database_knowledge: db_alias 可省略（扫描全部工作区）")
print()
if not ws.is_dir():
    print("（尚无 workspace 目录）")
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
        print(f"【{alias_dir.name}】")
        for p in mds:
            if p.name.startswith("_"):
                continue
            print(f"  - dataset/{p.relative_to(ds).as_posix()}")
        mp = alias_dir / "manifest.json"
        if mp.is_file():
            try:
                man = json.loads(mp.read_text(encoding="utf-8"))
                print(f"  manifest.projects: {len(man.get('projects') or [])} 个前端")
            except Exception:
                pass
```

## 标准流程（SOP）

### 0. 明确业务需求

弄清业务目标、范围、关注点；`business_goal` / `scope` 写入文档 YAML 头。

### 1. 先查 dataset（必做）

1. **`list_database_knowledge`**（建议传 `db_alias`）
2. **`read_database_knowledge`**（`db_alias` + `file_name`）
3. 不足或需刷新 → 步骤 2

可选：**`read_workspace_manifest`**（UI_build 工具）查看同工作区是否已有 config/frontend。

### 2. 连接客户数据库

**`database_connect`**（推荐 `use_workspace_config=true`）：

| 场景 | 参数 |
|------|------|
| 整理源库 A | `connection_mode="source"`, `database="源库名"` |
| 建表/写入 | `connection_mode="target"`（库名自动取 `target_database`） |

**勿在回复中写密码**；结束 **`database_disconnect`**。

### 3. 只读探查

`list_tables` → `describe_table` → `database_query`（只读 SQL）；样本须脱敏。

### 4. 写入 dataset

**`save_markdown`** 整文件写入；小改优先 **`patch_markdown`**（`old_string` / `new_string`）→ 更新 `manifest.json` 的 `knowledge_files`。

### 5. 收尾

说明工作区路径、是否命中旧文档、未覆盖表及待确认项。

若用户要 **完整业务系统**（不仅是知识文档），dataset 完成后须交接：

1. **backend** skill：`save_backend_file` 写 API（含 `main.py`）
2. **UI_build** skill：`save_ui_file` 写 `frontend/` 与 `preview.html`
3. 收尾前 **`verify_fullstack_deliverables`**（backend 工具）

**禁止**在只写完 dataset 的情况下声称「前端/全栈已完成」。

## 工具一览

| 工具 | 作用 |
|------|------|
| `list_database_knowledge` | 列举 dataset 下 md（可选 db_alias） |
| `read_database_knowledge` | 读取 md |
| `save_markdown` | 整文件保存 md |
| `patch_markdown` | 片段替换已有 md |
| `database_connect` / `database_disconnect` | 连库 / 断开 |
| `list_tables` / `describe_table` / `database_query` | 只读探查 |

## 依赖

MySQL：`pymysql`；PostgreSQL：`psycopg2-binary`；SQLite：内置。

## 编排层

`ensure_tools_loaded("database")`。与 **UI_build** 协作时使用相同 **`db_alias`**。
