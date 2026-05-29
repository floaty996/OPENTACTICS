"""民族分析路由 - 提供民族相关统计接口"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db import get_connection

router = APIRouter(tags=["民族分析"])


@router.get("/ethnic/overview")
async def get_ethnic_overview(
    nationality: Optional[str] = Query(None, description="按民族筛选"),
    department: Optional[str] = Query(None, description="按部门筛选"),
    line: Optional[str] = Query(None, description="按线路筛选"),
):
    """获取民族分析总览：总人数、民族种类数、少数民族占比、多样性指数"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 构建筛选条件
            where = []
            params = []
            if nationality:
                where.append("nationality = %s")
                params.append(nationality)
            if department:
                where.append("department = %s")
                params.append(department)
            if line:
                where.append("subway_line = %s")
                params.append(line)
            where_clause = "WHERE " + " AND ".join(where) if where else ""

            # 总员工数
            cur.execute(f"SELECT COUNT(*) AS total FROM metro_employees {where_clause}", params)
            total = cur.fetchone()["total"]

            # 民族种类数
            cur.execute(f"SELECT COUNT(DISTINCT nationality) AS cnt FROM metro_employees {where_clause}", params)
            ethnic_count = cur.fetchone()["cnt"]

            # 各民族人数
            cur.execute(f"""
                SELECT nationality, COUNT(*) AS cnt
                FROM metro_employees
                {where_clause}
                GROUP BY nationality
                ORDER BY cnt DESC
            """, params)
            rows = cur.fetchall()

            # 汉族人数
            han_count = next((r["cnt"] for r in rows if r["nationality"] == "汉族"), 0)
            minority_count = total - han_count
            minority_pct = round(minority_count / total * 100, 2) if total > 0 else 0

            # 多样性指数（Simpson index: 1 - Σ(pi²)）
            simpson = 1 - sum((r["cnt"] / total) ** 2 for r in rows) if total > 0 else 0

            # 民族分布详情
            distribution = []
            for r in rows:
                pct = round(r["cnt"] / total * 100, 2)
                distribution.append({
                    "nationality": r["nationality"],
                    "count": r["cnt"],
                    "percentage": pct,
                    "type": "汉族" if r["nationality"] == "汉族" else "少数民族"
                })

        return {
            "total_employees": total,
            "ethnic_count": ethnic_count,
            "han_count": han_count,
            "minority_count": minority_count,
            "minority_percentage": minority_pct,
            "diversity_index": round(simpson, 4),
            "distribution": distribution
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ethnic/by-department")
async def get_ethnic_by_department(
    nationality: Optional[str] = Query(None, description="按民族筛选"),
    department: Optional[str] = Query(None, description="按部门筛选"),
    line: Optional[str] = Query(None, description="按线路筛选"),
):
    """获取各部门民族分布（热力图数据），支持筛选"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = []
            params = []
            if nationality:
                where.append("nationality = %s")
                params.append(nationality)
            if department:
                where.append("department = %s")
                params.append(department)
            if line:
                where.append("subway_line = %s")
                params.append(line)
            where_clause = "WHERE " + " AND ".join(where) if where else ""

            cur.execute(f"""
                SELECT department, nationality, COUNT(*) AS cnt
                FROM metro_employees
                {where_clause}
                GROUP BY department, nationality
                ORDER BY department, cnt DESC
            """, params)
            rows = cur.fetchall()

            departments = sorted(set(r["department"] for r in rows))
            nationalities = sorted(set(r["nationality"] for r in rows))

            matrix = {d: {} for d in departments}
            for r in rows:
                matrix[r["department"]][r["nationality"]] = r["cnt"]

            series_data = []
            for d in departments:
                for n in nationalities:
                    series_data.append({
                        "department": d,
                        "nationality": n,
                        "count": matrix[d].get(n, 0)
                    })

            return {
                "departments": departments,
                "nationalities": nationalities,
                "data": series_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ethnic/by-line")
async def get_ethnic_by_line():
    """获取各线路民族分布"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT subway_line, nationality, COUNT(*) AS cnt
                FROM metro_employees
                GROUP BY subway_line, nationality
                ORDER BY subway_line, cnt DESC
            """)
            rows = cur.fetchall()
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ethnic/detail")
async def get_ethnic_detail(
    nationality: Optional[str] = Query(None, description="按民族筛选"),
    department: Optional[str] = Query(None, description="按部门筛选"),
    line: Optional[str] = Query(None, description="按线路筛选"),
):
    """获取民族明细数据，支持按民族/部门/线路筛选"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = []
            params = []
            if nationality:
                where.append("e.nationality = %s")
                params.append(nationality)
            if department:
                where.append("e.department = %s")
                params.append(department)
            if line:
                where.append("e.subway_line = %s")
                params.append(line)

            where_clause = "WHERE " + " AND ".join(where) if where else ""

            sql = f"""
                SELECT e.nationality, e.department, e.subway_line,
                       COUNT(*) AS emp_count,
                       ROUND(AVG(e.age), 1) AS avg_age,
                       ROUND(AVG(e.seniority), 1) AS avg_seniority,
                       ROUND(AVG(e.monthly_salary), 0) AS avg_salary,
                       SUM(CASE WHEN e.gender = '男' THEN 1 ELSE 0 END) AS male_count,
                       SUM(CASE WHEN e.gender = '女' THEN 1 ELSE 0 END) AS female_count,
                       SUM(CASE WHEN e.status = '在职' THEN 1 ELSE 0 END) AS active_count
                FROM metro_employees e
                {where_clause}
                GROUP BY e.nationality, e.department, e.subway_line
                ORDER BY e.nationality, emp_count DESC
            """
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ethnic/trend-by-seniority")
async def get_ethnic_trend_by_seniority():
    """各民族的工龄分布趋势"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT nationality,
                       CASE
                           WHEN seniority <= 2 THEN '0-2年'
                           WHEN seniority <= 5 THEN '3-5年'
                           WHEN seniority <= 10 THEN '6-10年'
                           WHEN seniority <= 15 THEN '11-15年'
                           ELSE '15年以上'
                       END AS seniority_range,
                       COUNT(*) AS cnt
                FROM metro_employees
                GROUP BY nationality, seniority_range
                ORDER BY nationality, seniority_range
            """)
            rows = cur.fetchall()
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/ethnic/filters")
async def get_filters():
    """获取筛选选项（部门列表、民族列表、线路列表）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT department FROM metro_employees ORDER BY department")
            departments = [r["department"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT nationality FROM metro_employees ORDER BY nationality")
            nationalities = [r["nationality"] for r in cur.fetchall()]

            cur.execute("SELECT DISTINCT subway_line FROM metro_employees ORDER BY subway_line")
            lines = [r["subway_line"] for r in cur.fetchall()]

        return {
            "departments": departments,
            "nationalities": nationalities,
            "lines": lines
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
