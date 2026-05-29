---
db_alias: "hr_project"
generated_at: "2026-05-27"
scope: "聚焦员工服务站点信息：站点服务记录表(metro_station_service) + 员工基础信息(metro_employees)中与服务站点相关的字段"
business_goal: "整理员工在各线路/站点的服务调配数据，支撑前端展示站点人力分布、在岗情况、调配历史等"
based_on: "20260414_metro_hr_domain.md（已有全库梳理）"
---

# 员工服务站点信息 — 专题知识

## 1. 业务背景与目标

- **业务场景**：地铁公司的人力资源管理中，需要清晰地知道每位员工当前在哪个线路/站点服务，以及历史服务记录，从而支撑站点人力调度、在岗监控、调配追踪等业务。
- **本次要搞清楚的问题**：
  - 员工服务站点有哪些核心字段和状态？
  - 如何区分"当前在岗"与"历史记录"？
  - 调配类型（常驻/轮岗/临时支援）的业务含义是什么？
  - 员工的基础所属 vs 实际服务站点如何关联？
- **不在本次范围**：员工个人属性（学历、职称等）的详细分析。

## 2. 核心实体与关系

### 2.1 涉及的表

| 业务实体 | 表名 | 数据量 | 说明 |
|----------|------|--------|------|
| 员工 | metro_employees | 1000条 | 员工主数据，含编制所属线路/站点 |
| 站点服务记录 | metro_station_service | 2035条 | 员工在各站点的实际服务调配记录 |

### 2.2 核心关系

```
metro_employees (1) ──── (N) metro_station_service
    员工                     员工的服务记录
  包含：编制所属线路          实际服务线路/站点
      编制所属站点          调配类型、时间段、工时
      基础属性              当前在岗状态
```

- **编制所属**：`metro_employees.subway_line` + `metro_employees.subway_station` → 员工行政上所属的线路和站点
- **实际服务**：`metro_station_service` 中的每一条记录 → 员工实际被调配到某线路/站点的服务记录

## 3. 关键表结构详述

### 3.1 `metro_employees` — 与服务站点相关的字段

| 字段 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| emp_id | varchar(8) | EMP00001 | 员工编号（PK） |
| name | varchar(32) | 张三 | 员工姓名 |
| subway_line | varchar(16) | 1号线 | **编制所属线路**（共5条线：1号线~5号线） |
| subway_station | varchar(64) | 建国门站 | **编制所属站点**（行政归属，不等于实际服务站点） |
| department | varchar(64) | 站务部 | 部门（10个部门） |
| job_position | varchar(64) | 站务员 | 岗位（41种） |
| status | varchar(16) | 在职 | **员工状态**：在职(680)/出差(153)/休假(167) |

### 3.2 `metro_station_service` — 站点服务记录

| 字段 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| service_id | varchar(16) | SRV00001 | 服务记录编号（PK） |
| emp_id | varchar(8) | EMP00001 | 员工编号（FK→metro_employees） |
| emp_name | varchar(32) | 张三 | 员工姓名（冗余字段） |
| subway_line | varchar(16) | 2号线 | **实际服务线路** |
| subway_station | varchar(64) | 朝阳门站 | **实际服务站点** |
| assignment_type | varchar(16) | 常驻 | **调配类型**：常驻 / 轮岗 / 临时支援 |
| service_start_date | date | 2026-01-01 | 该次服务开始日期 |
| service_end_date | date | NULL | 该次服务结束日期（NULL=仍在岗） |
| daily_start_time | time | 08:00:00 | 每日上班时间 |
| daily_end_time | time | 17:00:00 | 每日下班时间 |
| daily_duration_hours | decimal(4,1) | 8.0 | 每日工时（小时） |
| service_days | int | 30 | 该服务周期总天数 |
| total_service_hours | decimal(10,1) | 240.0 | 该服务周期总工时 |
| is_current | tinyint(1) | 1 | **当前在岗标识**：1=当前在岗，0=历史记录 |
| service_status | varchar(16) | 服务中 | **服务状态**：服务中 / 已结束 |
| remark | varchar(128) | NULL | 备注 |

## 4. 调配类型详解

| 调配类型 | 说明 | 特点 |
|----------|------|------|
| **常驻** | 员工长期固定在一个站点服务 | 周期较长(通常数月~数年)，稳定 |
| **轮岗** | 员工按周期在不同站点间轮换 | 周期性轮换，服务天数较短 |
| **临时支援** | 员工短期到其他站点支援 | 周期短，突发性需求 |

## 5. 状态判断逻辑（前端/业务常见判断）

### 5.1 当前在岗判断

一个员工**当前正在某站点服务**的判断条件（三个条件同时满足）：
```
is_current = 1
AND service_status = '服务中'
AND service_end_date IS NULL
```

### 5.2 员工状态与在岗状态的联动

| 员工状态(metro_employees.status) | 含义 |
|--------------------------------|------|
| 在职 | 正常在岗 / 可能正在某站点服务 |
| 出差 | 不在常规站点，有临时外派任务 |
| 休假 | 不在岗（年假/病假等） |

> 注意：员工在主表的状态与 `metro_station_service` 中的服务记录**可能不完全同步**，例如休假员工仍可能有之前未结束的服务记录。

### 5.3 编制 vs 实际服务

- **编制所属**（employees表）≠ **实际服务站点**（service表）
- 一个员工可能编制在1号线建国门站，但被临时调配到2号线朝阳门站服务
- 这反映了实际业务中灵活调度的需求

## 6. 常见查询模式（供前端参考）

### 6.1 查询当前在某站点服务的所有员工
```sql
SELECT e.emp_id, e.name, e.job_position, e.department,
       s.subway_line, s.subway_station, s.assignment_type,
       s.daily_start_time, s.daily_end_time
FROM metro_station_service s
JOIN metro_employees e ON s.emp_id = e.emp_id
WHERE s.subway_station = '某站点'
  AND s.is_current = 1
  AND s.service_status = '服务中'
  AND s.service_end_date IS NULL;
```

### 6.2 查询某个员工的所有服务记录（历史+当前）
```sql
SELECT * FROM metro_station_service
WHERE emp_id = 'EMP00001'
ORDER BY service_start_date DESC;
```

### 6.3 各站点的当前人力分布统计
```sql
SELECT subway_line, subway_station, COUNT(*) as current_staff
FROM metro_station_service
WHERE is_current = 1 AND service_status = '服务中'
GROUP BY subway_line, subway_station
ORDER BY subway_line, subway_station;
```

## 7. 待确认事项

1. **编制 vs 实际服务不一致时**：前端展示应以实际服务记录为准，还是同时展示两者？建议实际服务站点为主，编制所属为辅。
2. **批量查看的需求**：是否需要一个页面展示所有站点的当前人力分布热力图？
3. **调配审批流程**：`assignment_type` 的变更是否有审批流程？前端是否需要提交调配申请入口？
4. **排班视图**：是否需要以日历/时间线方式展示员工在各站点的服务排班？

## 8. 附录

- **分析依据**：基于 `20260414_metro_hr_domain.md` 二次整理
- **表名**：`basic_data` 库下的 `metro_employees`、`metro_station_service`
- **已连接的源库**：`basic_data`（本次因 pymysql 模块缺失未直连，已用既有知识文档）
