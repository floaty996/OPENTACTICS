"""
根据 metro_employees 表中的现职人员，生成工作站点服务记录并写入 MySQL。

记录每位员工在各站点的服务起止日期、每日班次、服务天数、累计服务时长等指标。

运行前：
  1. 已执行 create_data.py，metro_employees 表中有数据
  2. config/database.json 已配置 MySQL 连接
  3. pip install pandas pymysql
  4. python create_station_service_data.py
"""

from __future__ import annotations

import json
import random
import string
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql
from pymysql.cursors import DictCursor

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config" / "database.json"

EMPLOYEE_TABLE_DEFAULT = "metro_employees"
SERVICE_TABLE_DEFAULT = "metro_station_service"
ACTIVE_STATUSES = ("在职", "出差")

# 每条服务记录：中文列名 -> 数据库字段
COLUMN_MAP: dict[str, str] = {
    "服务记录ID": "service_id",
    "工号": "emp_id",
    "姓名": "emp_name",
    "所属线路": "subway_line",
    "服务站点": "subway_station",
    "派遣类型": "assignment_type",
    "服务开始日期": "service_start_date",
    "服务结束日期": "service_end_date",
    "每日开始时间": "daily_start_time",
    "每日结束时间": "daily_end_time",
    "每日服务时长(小时)": "daily_duration_hours",
    "服务天数": "service_days",
    "累计服务时长(小时)": "total_service_hours",
    "是否当前站点": "is_current",
    "服务状态": "service_status",
    "备注": "remark",
}

INSERT_COLUMNS = list(COLUMN_MAP.values())

ASSIGNMENT_TYPES = ("常驻", "临时支援", "轮岗")
SHIFT_TEMPLATES = [
    (time(6, 0), time(14, 0)),
    (time(8, 0), time(17, 0)),
    (time(9, 0), time(18, 0)),
    (time(14, 0), time(22, 0)),
    (time(7, 30), time(19, 30)),
]

subway_lines = ["1号线", "2号线", "3号线", "4号线", "5号线"]
subway_stations: dict[str, list[str]] = {
    line: [f"{line}{i}站" for i in range(1, 14)] for line in subway_lines
}


def load_db_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到 {_CONFIG_PATH}，请先配置 MySQL 连接（参考 config/database.example.json）。"
        )
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)

    config.setdefault("db_type", "mysql")
    config.setdefault("port", 3306)
    config.setdefault("clear_before_insert", True)
    config.setdefault("records_per_employee_min", 1)
    config.setdefault("records_per_employee_max", 4)

    # 与 create_data.py 共用 database.json：table_name 表示员工表
    config.setdefault("employee_table", config.get("table_name", EMPLOYEE_TABLE_DEFAULT))
    config.setdefault("service_table", SERVICE_TABLE_DEFAULT)

    if config["service_table"] == config["employee_table"]:
        raise ValueError(
            "service_table 不能与 employee_table 相同，请在 database.json 中设置 "
            f'"service_table": "{SERVICE_TABLE_DEFAULT}"'
        )

    if config["db_type"].lower() != "mysql":
        raise ValueError("本脚本仅支持 MySQL。")
    for key in ("host", "user", "database"):
        if not config.get(key):
            raise ValueError(f"MySQL 配置缺少必填项: {key}")
    return config


def _quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def connect_mysql(config: dict[str, Any]) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config.get("password", ""),
        database=config["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


def create_service_table_sql(table_name: str) -> str:
    t = _quote_ident(table_name)
    return f"""
    CREATE TABLE IF NOT EXISTS {t} (
        `service_id` VARCHAR(16) NOT NULL,
        `emp_id` VARCHAR(8) NOT NULL,
        `emp_name` VARCHAR(32) NOT NULL,
        `subway_line` VARCHAR(16) NOT NULL,
        `subway_station` VARCHAR(64) NOT NULL,
        `assignment_type` VARCHAR(16) NOT NULL,
        `service_start_date` DATE NOT NULL,
        `service_end_date` DATE NULL,
        `daily_start_time` TIME NOT NULL,
        `daily_end_time` TIME NOT NULL,
        `daily_duration_hours` DECIMAL(4,1) NOT NULL,
        `service_days` INT NOT NULL,
        `total_service_hours` DECIMAL(10,1) NOT NULL,
        `is_current` TINYINT(1) NOT NULL DEFAULT 0,
        `service_status` VARCHAR(16) NOT NULL,
        `remark` VARCHAR(128) NULL,
        PRIMARY KEY (`service_id`),
        KEY `idx_emp_id` (`emp_id`),
        KEY `idx_station` (`subway_line`, `subway_station`),
        KEY `idx_current` (`is_current`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """


def _employee_table_stats(config: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    emp_table = _quote_ident(config["employee_table"])
    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {emp_table}")
            total = int(cur.fetchone()["cnt"])
            cur.execute(
                f"SELECT status, COUNT(*) AS cnt FROM {emp_table} GROUP BY status ORDER BY cnt DESC"
            )
            breakdown = cur.fetchall()
    finally:
        conn.close()
    return total, breakdown


def _ensure_employee_data(config: dict[str, Any]) -> None:
    total, _ = _employee_table_stats(config)
    if total > 0:
        return
    script = _ROOT / "create_data.py"
    print("=" * 80)
    print(f"表 {config['employee_table']} 为空（可能曾被误清空），正在自动执行 create_data.py …")
    print("=" * 80)
    subprocess.run([sys.executable, str(script)], cwd=_ROOT, check=True)


def fetch_active_employees(config: dict[str, Any]) -> list[dict[str, Any]]:
    _ensure_employee_data(config)

    emp_table = _quote_ident(config["employee_table"])
    placeholders = ", ".join(["%s"] * len(ACTIVE_STATUSES))
    sql = f"""
        SELECT emp_id, name AS emp_name, subway_line, subway_station,
               hire_date, status, job_position, department
        FROM {emp_table}
        WHERE status IN ({placeholders})
        ORDER BY emp_id
    """
    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, ACTIVE_STATUSES)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        total, breakdown = _employee_table_stats(config)
        detail = ", ".join(f"{r['status']}:{r['cnt']}" for r in breakdown) if breakdown else "（无记录）"
        raise RuntimeError(
            f"表 {config['employee_table']} 共 {total} 人，但无现职人员（需要 status 为 {ACTIVE_STATUSES}）。\n"
            f"当前状态分布: {detail}\n"
            "请运行: python create_data.py"
        )
    return rows


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _hours_between(start: time, end: time) -> Decimal:
    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute
    if end_mins <= start_mins:
        end_mins += 24 * 60
    return Decimal(str(round((end_mins - start_mins) / 60, 1)))


def _random_date_between(start: date, end: date) -> date:
    if start > end:
        start, end = end, start
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def _pick_station(line: str, exclude: str | None = None) -> str:
    candidates = [s for s in subway_stations[line] if s != exclude]
    return random.choice(candidates or subway_stations[line])


def _gen_service_id(emp_id: str, seq: int) -> str:
    suffix = "".join(random.choices(string.digits, k=4))
    return f"SR{emp_id[-4:]}{seq:02d}{suffix}"[:16]


def _build_record(
    emp: dict[str, Any],
    *,
    seq: int,
    line: str,
    station: str,
    assignment_type: str,
    start: date,
    end: date | None,
    is_current: bool,
    today: date,
) -> dict[str, Any]:
    daily_start, daily_end = random.choice(SHIFT_TEMPLATES)
    daily_hours = _hours_between(daily_start, daily_end)
    service_days = (end - start).days + 1 if end else (today - start).days + 1
    service_days = max(service_days, 1)
    total_hours = (daily_hours * service_days).quantize(Decimal("0.1"))

    if is_current:
        service_status = "服务中"
        remark = "当前在岗站点"
    else:
        service_status = "已结束"
        remark = random.choice(["轮岗结束", "支援任务完成", "调回原站点", ""])

    return {
        "服务记录ID": _gen_service_id(emp["emp_id"], seq),
        "工号": emp["emp_id"],
        "姓名": emp["emp_name"],
        "所属线路": line,
        "服务站点": station,
        "派遣类型": assignment_type,
        "服务开始日期": start.strftime("%Y-%m-%d"),
        "服务结束日期": end.strftime("%Y-%m-%d") if end else None,
        "每日开始时间": daily_start.strftime("%H:%M:%S"),
        "每日结束时间": daily_end.strftime("%H:%M:%S"),
        "每日服务时长(小时)": float(daily_hours),
        "服务天数": service_days,
        "累计服务时长(小时)": float(total_hours),
        "是否当前站点": 1 if is_current else 0,
        "服务状态": service_status,
        "备注": remark or None,
    }


def generate_station_services(
    employees: list[dict[str, Any]],
    config: dict[str, Any],
) -> pd.DataFrame:
    today = date.today()
    records: list[dict[str, Any]] = []
    min_rec = int(config["records_per_employee_min"])
    max_rec = int(config["records_per_employee_max"])

    for emp in employees:
        hire = _parse_date(emp["hire_date"])
        home_line = emp["subway_line"]
        home_station = emp["subway_station"]
        total_records = random.randint(min_rec, max_rec)

        # 当前在岗记录：固定在所属站点或同线路站点
        current_station = home_station if random.random() < 0.85 else _pick_station(home_line)
        current_start = _random_date_between(
            max(hire, today - timedelta(days=365)),
            today - timedelta(days=7),
        )
        records.append(
            _build_record(
                emp,
                seq=0,
                line=home_line,
                station=current_station,
                assignment_type="常驻" if current_station == home_station else random.choice(("临时支援", "轮岗")),
                start=current_start,
                end=None,
                is_current=True,
                today=today,
            )
        )

        # 历史服务记录
        for i in range(1, total_records):
            hist_line = home_line if random.random() < 0.7 else random.choice(subway_lines)
            hist_station = _pick_station(hist_line, exclude=home_station if hist_line == home_line else None)
            hist_end = _random_date_between(hire + timedelta(days=30), today - timedelta(days=30))
            span_days = random.randint(30, min(720, (hist_end - hire).days or 30))
            hist_start = hist_end - timedelta(days=span_days)
            if hist_start < hire:
                hist_start = hire + timedelta(days=1)

            records.append(
                _build_record(
                    emp,
                    seq=i,
                    line=hist_line,
                    station=hist_station,
                    assignment_type=random.choice(ASSIGNMENT_TYPES),
                    start=hist_start,
                    end=hist_end,
                    is_current=False,
                    today=today,
                )
            )

    return pd.DataFrame(records)


def prepare_rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"数据缺少字段: {missing}")
    prepared = df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)
    return [tuple(row) for row in prepared.itertuples(index=False, name=None)]


def ensure_service_table(cur: pymysql.cursors.Cursor, table_name: str) -> None:
    """若表不存在或结构不对（缺 service_id），则重建服务记录表。"""
    t = _quote_ident(table_name)
    cur.execute("SHOW TABLES LIKE %s", (table_name,))
    exists = cur.fetchone() is not None
    if exists:
        cur.execute(f"SHOW COLUMNS FROM {t} LIKE 'service_id'")
        if not cur.fetchone():
            cur.execute(f"DROP TABLE {t}")
            exists = False
    if not exists:
        cur.execute(create_service_table_sql(table_name))


def write_to_mysql(df: pd.DataFrame, config: dict[str, Any]) -> int:
    table_name = config["service_table"]
    rows = prepare_rows(df)
    t = _quote_ident(table_name)
    cols = ", ".join(_quote_ident(c) for c in INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    insert_sql = f"INSERT INTO {t} ({cols}) VALUES ({placeholders})"

    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            ensure_service_table(cur, table_name)
            if config.get("clear_before_insert", True):
                cur.execute(f"TRUNCATE TABLE {t}")
            cur.executemany(insert_sql, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(rows)


def print_summary(df: pd.DataFrame, employee_count: int) -> None:
    print("=" * 80)
    print("工作人员工作站点服务表 - 数据概览")
    print("=" * 80)
    print(f"现职人员数: {employee_count}")
    print(f"服务记录数: {len(df)}  （人均约 {len(df) / employee_count:.1f} 条）")
    print(f"字段: {', '.join(df.columns)}")

    print("\n前10条记录预览:")
    print(df.head(10).to_string(index=False))

    print("\n派遣类型分布:")
    for t, cnt in df["派遣类型"].value_counts().items():
        print(f"  {t}: {cnt}条")

    print("\n服务状态分布:")
    for s, cnt in df["服务状态"].value_counts().items():
        print(f"  {s}: {cnt}条")

    current = df[df["是否当前站点"] == 1]
    print(f"\n当前在岗站点记录: {len(current)} 条")
    print(f"累计服务时长(小时) 均值: {df['累计服务时长(小时)'].mean():.1f}")
    print(f"每日服务时长(小时) 均值: {df['每日服务时长(小时)'].mean():.1f}")


def main() -> None:
    random.seed(42)
    config = load_db_config()

    employees = fetch_active_employees(config)
    df = generate_station_services(employees, config)
    print_summary(df, len(employees))

    inserted = write_to_mysql(df, config)

    print("\n" + "=" * 80)
    print("工作站点服务数据已写入 MySQL")
    print(f"主机: {config['host']}:{config['port']}")
    print(f"库名: {config['database']}")
    print(f"员工表: {config['employee_table']}")
    print(f"服务记录表: {config['service_table']}")
    print(f"写入记录数: {inserted}")
    print("=" * 80)


if __name__ == "__main__":
    main()
