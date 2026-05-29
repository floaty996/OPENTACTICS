---
db_alias: "zhicheng"
project_name: "title-system-api"
generated_at: "2026-05-28"
framework: "FastAPI + Uvicorn"
linked_frontend: "title-system-web"
---

# 员工职称管理系统 - API 知识文档

## 1. 路由一览

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/employees` | 员工列表（分页+搜索+部门筛选） |
| GET | `/api/employees/by-title` | 按职称筛选员工（参数：professional_title, department, page, page_size） |
| GET | `/api/employees/{emp_id}` | 员工详情 |
| GET | `/api/employees/departments` | 部门列表（去重） |
| POST | `/api/applications` | 提交职称申请 |
| GET | `/api/applications` | 申请列表（分页+状态/部门筛选） |
| GET | `/api/applications/{id}` | 申请详情 |
| PUT | `/api/applications/{id}/review` | 审批申请（通过/驳回） |
| GET | `/api/statistics/overview` | 系统概览数据 |
| GET | `/api/statistics/title-distribution` | 部门职称分布（可选部门筛选）|
| GET | `/api/statistics/title-by-education` | 学历 vs 职称分布 |

> 所有路由同时支持无 `/api` 前缀的版本（如 `GET /employees` 同等于 `GET /api/employees`），方便不同前端接入方式。

## 2. 数据源

- **源库 basic_data**：`metro_employees` 表（只读查询）
- **目标库 allocation**：`title_application` 表（可写，存储申请/审批记录）

## 3. 请求与响应示例

### POST `/api/applications`
```json
// 请求
{ "emp_id": "E001", "applied_title": "中级职称", "reason": "工作表现优秀" }
// 响应
{ "ok": true, "message": "申请已提交", "id": 1 }
```

### PUT `/api/applications/{id}/review`
```json
// 请求
{ "reviewer": "管理员", "review_comment": "同意晋升", "action": "approve" }
// 响应
{ "ok": true, "message": "申请已通过" }
```

## 4. 业务规则

- **职称晋升等级**：无职称(0) → 初级职称(1) → 中级职称(2) → 高级职称(3)，不可跨级跳
- **申请校验**：自动从 `metro_employees` 获取当前职称，`applied_title` 必须高于当前
- **审批通过**：自动更新 `metro_employees.professional_title` 为申请职称
- **审批驳回**：仅变更申请状态，不影响员工原职称

## 5. 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 参数校验失败（如职称未提升、重复处理） |
| 404 | 员工或申请不存在 |

## 6. 启动信息

- **端口**：8000
- **API 前缀**：`/api`（同时支持无前缀）
- **启动命令**：`uvicorn main:app --reload --port 8000`
- **前端对接**：Vite 代理 `/api` → `http://127.0.0.1:8000`
