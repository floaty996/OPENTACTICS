---
title: 站点人员信息系统 API 文档
db_alias: test2
version: 2.0.0
---

## 数据源

- **源库** `basic_data`（只读）：`metro_employees` 员工表（1000人）、`metro_station_service` 服务记录表
- **目标库** `allocation`（读写）：`station_transfers` 换站申请表

## 路由表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stations` | 站点列表（从员工表 DISTINCT） |
| GET | `/api/stations/{id}` | 站点详情及员工列表 |
| GET | `/api/employees` | 员工列表（支持线路/站点/职位/状态/关键词筛选） |
| GET | `/api/employees/{employee_no}` | 员工详情 |
| GET | `/api/employees/analysis/summary` | 人员统计分析 |
| GET | `/api/transfers` | 申请列表（支持状态/员工编号筛选） |
| GET | `/api/transfers/{id}` | 申请详情 |
| POST | `/api/transfers` | 提交换站申请 |
| PUT | `/api/transfers/{id}/approve` | 审批申请（通过/驳回） |

## 员工字段映射

后端返回字段（源库 metro_employees）：

| 字段 | 含义 |
|------|------|
| employee_no | 工号（emp_id） |
| name | 姓名 |
| gender | 性别 |
| age | 年龄 |
| subway_line | 地铁线路 |
| subway_station | 地铁站名 |
| department | 部门 |
| position | 职位（job_position） |
| education | 学历 |
| professional_title | 职称 |
| hire_date | 入职日期 |
| seniority | 工龄 |
| status | 状态（active/inactive） |

站点字段：`id, subway_line, name(subway_station), employee_count`

换站申请字段（allocation.station_transfers）：
`id, employee_no, employee_name, from_subway_line, from_subway_station, to_subway_line, to_subway_station, reason, status, apply_date, approve_date, approver, reject_reason`
