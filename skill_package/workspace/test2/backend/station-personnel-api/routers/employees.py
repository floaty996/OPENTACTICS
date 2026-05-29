"""
员工信息相关路由 — 读取目标库 allocation.employee_station（可写，审批后可更新）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from database import fetch_all_target, fetch_one_target

router = APIRouter(prefix="/api/employees", tags=["员工管理"])


@router.get("")
def list_employees(
    subway_line: str | None = Query(None, description="按线路筛选"),
    subway_station: str | None = Query(None, description="按站点筛选"),
    position: str | None = Query(None, description="按职位筛选"),
    keyword: str | None = Query(None, description="按姓名/工号搜索"),
):
    """获取员工列表，支持筛选"""
    sql = """
        SELECT employee_no, employee_name AS name,
               subway_line, subway_station,
               department, job_position AS position,
               status
        FROM employee_station
        WHERE 1=1
    """
    params: list = []
    if subway_line:
        sql += " AND subway_line = %s"
        params.append(subway_line)
    if subway_station:
        sql += " AND subway_station = %s"
        params.append(subway_station)
    if position:
        sql += " AND job_position = %s"
        params.append(position)
    if keyword:
        sql += " AND (employee_name LIKE %s OR employee_no LIKE %s)"
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    sql += " ORDER BY employee_no LIMIT 200"
    return fetch_all_target(sql, params)


@router.get("/{employee_no}")
def get_employee(employee_no: str):
    """根据员工编号查询单个员工详情"""
    row = fetch_one_target(
        "SELECT employee_no, employee_name AS name,"
        " subway_line, subway_station, department, job_position AS position, status"
        " FROM employee_station WHERE employee_no = %s", [employee_no]
    )
    if not row:
        raise HTTPException(status_code=404, detail="员工不存在")
    return row


@router.get("/analysis/summary")
def employee_summary():
    """员工信息统计分析"""
    total_row = fetch_one_target("SELECT COUNT(*) AS total FROM employee_station")
    total_employees = total_row["total"] if total_row else 0

    by_station = fetch_all_target("""
        SELECT subway_station AS station_name, subway_line,
               COUNT(*) AS employee_count
        FROM employee_station
        GROUP BY subway_line, subway_station
        ORDER BY employee_count DESC
        LIMIT 50
    """)

    by_position = fetch_all_target("""
        SELECT job_position AS position, COUNT(*) AS count
        FROM employee_station
        GROUP BY job_position
        ORDER BY count DESC
    """)

    departments = fetch_all_target("""
        SELECT department, COUNT(*) AS count
        FROM employee_station
        GROUP BY department
        ORDER BY count DESC
    """)

    return {
        "total_employees": total_employees,
        "by_station": by_station,
        "by_position": by_position,
        "department_stats": departments,
    }
