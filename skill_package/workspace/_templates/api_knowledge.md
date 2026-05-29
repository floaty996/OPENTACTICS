---
db_alias: "{客户库别名}"
project_name: "{后端工程名}"
linked_frontend: "{前端工程名}"
generated_at: "{YYYY-MM-DD}"
api_prefix: "/api"
default_port: 8000
---

# {工程名} — 后端 API 知识

## 1. 服务目标

## 2. 技术栈与运行方式

- 默认：FastAPI + Uvicorn
- 启动：`uvicorn main:app --reload --port 8000`

## 3. 数据库连接约定

- 源库（只读）：`database_connect(connection_mode="source", ...)`
- 目标库（可写）：`database_connect(connection_mode="target", ...)`
- 表结构见 `dataset/*.md`

## 4. REST 接口一览

| 方法 | 路径 | 说明 | 主要表 |
|------|------|------|--------|
| GET | /api/... | | |

## 5. 请求 / 响应示例

## 6. 与前端对接

- 前端工程：`frontend/{linked_frontend}/`
- 开发环境 API 基址：`http://127.0.0.1:8000/api`
- CORS：已在后端配置

## 7. 变更记录

| 日期 | 说明 |
|------|------|
