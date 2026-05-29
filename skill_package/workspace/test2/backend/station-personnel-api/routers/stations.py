"""
站点信息相关路由 — 从目标库 employee_station 提取站点列表
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from database import fetch_all_target, fetch_one_target

router = APIRouter(prefix="/api/stations", tags=["站点管理"])


@router.get("")
@router.get("/")
def list_stations():
    """获取所有站点列表（从 employee_station DISTINCT）"""
    return fetch_all_target("""
        SELECT
            ROW_NUMBER() OVER (ORDER BY subway_line, subway_station) AS id,
            subway_line,
            subway_station AS name,
            COUNT(*) AS employee_count
        FROM employee_station
        GROUP BY subway_line, subway_station
        ORDER BY subway_line, subway_station
    """)


@router.get("/{station_id}")
def get_station(station_id: int):
    """获取单个站点详情及员工列表"""
    stations = fetch_all_target("""
        SELECT
            ROW_NUMBER() OVER (ORDER BY subway_line, subway_station) AS id,
            subway_line,
            subway_station AS name
        FROM employee_station
        GROUP BY subway_line, subway_station
        ORDER BY subway_line, subway_station
    """)
    target = None
    for s in stations:
        if s["id"] == station_id:
            target = s
            break
    if not target:
        raise HTTPException(status_code=404, detail="站点不存在")

    employees = fetch_all_target("""
        SELECT employee_no, employee_name AS name,
               job_position AS position, department, status
        FROM employee_station
        WHERE subway_line = %s AND subway_station = %s
        ORDER BY employee_no
    """, [target["subway_line"], target["name"]])

    return {**target, "employees": employees}
