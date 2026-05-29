---
db_alias: "zhicheng"
project_name: "title-system-web"
generated_at: "2026-05-28"
framework: "React + Vite + TypeScript"
---

# 员工职称管理系统 - UI 知识文档

## 1. 页面架构

| 页面 | 路由 | 说明 |
|------|------|------|
| 分布概览 | `/` | 统计卡片 + 图表（部门分布、学历交叉） |
| 职称申请 | `/apply` | 员工列表 + 申请弹窗 |
| 职称审批 | `/approve` | 申请列表 + 审批弹窗（通过/驳回） |

## 2. 布局与交互

- **侧边栏导航**：左侧固定宽 220px（响应式缩至 60px），深色背景渐变
- **主内容区**：flex 自适应，padding 24px
- **页面切换**：Tab 切换，无路由跳转（SPA 风格），当前使用原生 display 控制
- **响应式断点**：900px 以下侧边栏收缩为图标

## 3. 色彩体系

| 用途 | 色值 |
|------|------|
| 侧边栏 | `#001529` → `#002140` 渐变 |
| 主色调（蓝色） | `#1890ff` |
| 成功/通过 | `#52c41a` |
| 危险/驳回 | `#ff4d4f` |
| 警告/待审批 | `#fa8c16` |

## 4. 职称等级配色

| 等级 | 标签色 |
|------|--------|
| 无职称 | 蓝色 (`#1890ff`) |
| 初级职称 | 深蓝 (`#2f54eb`) |
| 中级职称 | 橙色 (`#d46b08`) |
| 高级职称 | 红色 (`#cf1322`) |

## 5. 组件风格

- 卡片容器：白底 + 8px 圆角 + 浅阴影
- 表格：无边框表头灰色背景，hover 行高亮
- 按钮：带图标、圆角 6px、hover 色加深
- 标签（Tag）：胶囊形圆角 12px
- 弹窗模态：居中、遮罩半透明灰、表单字段带 focus 蓝色边框

## 6. 接口约定

| 后端路由 | 方法 | 前端用途 |
|----------|------|----------|
| `/api/employees` | GET | 员工列表（搜索+分页） |
| `/api/employees/{emp_id}` | GET | 单个员工详情 |
| `/api/employees/departments` | GET | 部门下拉列表 |
| `/api/applications` | GET | 申请列表（筛选+分页） |
| `/api/applications` | POST | 提交职称申请 |
| `/api/applications/{id}` | GET | 申请详情 |
| `/api/applications/{id}/review` | PUT | 审批（通过/驳回） |
| `/api/statistics/overview` | GET | 概览统计卡片 |
| `/api/statistics/title-distribution` | GET | 部门职称分布（支持筛选） |
| `/api/statistics/title-by-education` | GET | 学历 vs 职称分布 |

API 基址：`http://127.0.0.1:8000/api`

## 7. 数据处理逻辑

- 申请提交时校验「申请的职称必须高于当前职称」由后端执行
- 审批通过后后端自动更新 `metro_employees` 的 `professional_title`
- 图表使用 ECharts，堆叠柱状图展示分布

## 8. 版本记录

- 2026-05-28：v1.0 创建，三个页面 + API 对接
