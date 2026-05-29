"""
根据现职员工生成「换工作站点申请」虚拟数据并写入 MySQL。

运行前：
  1. 已执行 create_data.py（metro_employees 有数据）
  2. config/database.json 已配置 MySQL
  3. pip install pandas pymysql
  4. python create_station_transfer_data.py
"""

from __future__ import annotations

import json
import random
import string
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql
from pymysql.cursors import DictCursor

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config" / "database.json"

EMPLOYEE_TABLE_DEFAULT = "metro_employees"
SERVICE_TABLE_DEFAULT = "metro_station_service"
APPLICATION_TABLE_DEFAULT = "metro_station_transfer_application"
ACTIVE_STATUSES = ("在职", "出差")

COLUMN_MAP: dict[str, str] = {
    "申请单号": "application_id",
    "工号": "emp_id",
    "姓名": "emp_name",
    "部门": "department",
    "岗位": "job_position",
    "当前线路": "current_subway_line",
    "当前站点": "current_subway_station",
    "目标线路": "target_subway_line",
    "目标站点": "target_subway_station",
    "申请类型": "application_type",
    "申请原因": "application_reason",
    "申请日期": "application_date",
    "期望换站日期": "expected_transfer_date",
    "紧急程度": "urgency_level",
    "审批状态": "approval_status",
    "审批人": "approver_name",
    "审批日期": "approval_date",
    "审批意见": "approval_comment",
    "审批耗时(天)": "approval_days",
    "流程状态": "process_status",
}

INSERT_COLUMNS = list(COLUMN_MAP.values())

APPLICATION_TYPES = ("同线换站", "跨线换站")
URGENCY_LEVELS = ("普通", "紧急")
APPROVAL_STATUSES = ("待审批", "已通过", "已驳回", "已撤回")
PROCESS_STATUS_MAP = {
    "待审批": "审批中",
    "已通过": "已完成",
    "已驳回": "已关闭",
    "已撤回": "已取消",
}

APPLICATION_REASONS = [
    "家庭住址变更，当前站点通勤时间过长",
    "配偶工作调动，希望调整至就近站点",
    "个人专业技能与目标站点岗位需求更匹配",
    "原站点人员配置饱和，申请调剂至缺人站点",
    "职业发展需要，申请前往业务拓展站点锻炼",
    "健康原因需缩短通勤距离，申请换至较近站点",
    "子女入学地点变更，需调整工作站点方便接送",
    "完成当前站点阶段性任务，申请轮换至其他站点",
]

APPROVERS = [
    "站务部经理-刘强",
    "人力资源部主管-陈静",
    "运营调度中心主任-王磊",
    "运营管理部副经理-赵敏",
    "安全监察部主管-孙涛",
]

APPROVAL_COMMENTS_APPROVED = [
    "符合站点人员调剂政策，同意换站。",
    "目标站点确有岗位空缺，同意申请。",
    "申请人司龄及考核达标，批准换站。",
    "已与目标站点站长沟通，同意接收。",
]

APPROVAL_COMMENTS_REJECTED = [
    "目标站点暂无空缺，建议三个月后重新申请。",
    "申请人当前岗位为关键岗位，暂不适合调动。",
    "跨线换站需额外培训，当前不满足条件。",
    "近期站点人员调整频繁，暂不批准换站。",
]

subway_lines = ["1号线", "2号线", "3号线", "4号线", "5号线"]
subway_stations: dict[str, list[str]] = {
    line: [f"{line}{i}站" for i in range(1, 14)] for line in subway_lines
}


def load_db_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"未找到 {_CONFIG_PATH}，请先配置 MySQL 连接。")
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)

    config.setdefault("db_type", "mysql")
    config.setdefault("port", 3306)
    config.setdefault("employee_table", config.get("table_name", EMPLOYEE_TABLE_DEFAULT))
    config.setdefault("service_table", SERVICE_TABLE_DEFAULT)
    config.setdefault("application_table", APPLICATION_TABLE_DEFAULT)
    config.setdefault("clear_before_insert", True)
    config.setdefault("application_count", 400)
    config.setdefault("max_applications_per_employee", 2)

    tables = {
        config["employee_table"],
        config["service_table"],
        config["application_table"],
    }
    if len(tables) != len(set(tables)):
        raise ValueError("employee_table、service_table、application_table 不能相同。")

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


def create_application_table_sql(table_name: str) -> str:
    t = _quote_ident(table_name)
    return f"""
    CREATE TABLE IF NOT EXISTS {t} (
        `application_id` VARCHAR(16) NOT NULL,
        `emp_id` VARCHAR(8) NOT NULL,
        `emp_name` VARCHAR(32) NOT NULL,
        `department` VARCHAR(64) NOT NULL,
        `job_position` VARCHAR(64) NOT NULL,
        `current_subway_line` VARCHAR(16) NOT NULL,
        `current_subway_station` VARCHAR(64) NOT NULL,
        `target_subway_line` VARCHAR(16) NOT NULL,
        `target_subway_station` VARCHAR(64) NOT NULL,
        `application_type` VARCHAR(16) NOT NULL,
        `application_reason` VARCHAR(256) NOT NULL,
        `application_date` DATE NOT NULL,
        `expected_transfer_date` DATE NOT NULL,
        `urgency_level` VARCHAR(8) NOT NULL,
        `approval_status` VARCHAR(16) NOT NULL,
        `approver_name` VARCHAR(64) NULL,
        `approval_date` DATE NULL,
        `approval_comment` VARCHAR(256) NULL,
        `approval_days` INT NULL,
        `process_status` VARCHAR(16) NOT NULL,
        PRIMARY KEY (`application_id`),
        KEY `idx_emp_id` (`emp_id`),
        KEY `idx_approval_status` (`approval_status`),
        KEY `idx_application_date` (`application_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """


def _employee_table_stats(config: dict[str, Any]) -> int:
    emp_table = _quote_ident(config["employee_table"])
    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {emp_table}")
            return int(cur.fetchone()["cnt"])
    finally:
        conn.close()


def _ensure_employee_data(config: dict[str, Any]) -> None:
    if _employee_table_stats(config) > 0:
        return
    script = _ROOT / "create_data.py"
    print("=" * 80)
    print(f"表 {config['employee_table']} 为空，正在自动执行 create_data.py …")
    print("=" * 80)
    subprocess.run([sys.executable, str(script)], cwd=_ROOT, check=True)


def fetch_active_employees(config: dict[str, Any]) -> list[dict[str, Any]]:
    _ensure_employee_data(config)
    emp_table = _quote_ident(config["employee_table"])
    placeholders = ", ".join(["%s"] * len(ACTIVE_STATUSES))
    sql = f"""
        SELECT emp_id, name AS emp_name, subway_line, subway_station,
               department, job_position, hire_date, status
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
        raise RuntimeError(
            f"表 {config['employee_table']} 中无现职人员，请先运行: python create_data.py"
        )
    return rows


def fetch_current_stations(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """从服务记录表读取当前在岗站点；无记录则回退到员工所属站点。"""
    service_table = config["service_table"]
    conn = connect_mysql(config)
    mapping: dict[str, dict[str, str]] = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (service_table,))
            if not cur.fetchone():
                return mapping
            t = _quote_ident(service_table)
            cur.execute(
                f"""
                SELECT emp_id, subway_line, subway_station
                FROM {t}
                WHERE is_current = 1
                """
            )
            for row in cur.fetchall():
                mapping[row["emp_id"]] = {
                    "subway_line": row["subway_line"],
                    "subway_station": row["subway_station"],
                }
    finally:
        conn.close()
    return mapping


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _random_date_between(start: date, end: date) -> date:
    if start > end:
        start, end = end, start
    return start + timedelta(days=random.randint(0, (end - start).days))


def _pick_target_station(current_line: str, current_station: str) -> tuple[str, str, str]:
    cross_line = random.random() < 0.35
    target_line = random.choice([ln for ln in subway_lines if ln != current_line]) if cross_line else current_line
    app_type = "跨线换站" if cross_line else "同线换站"
    candidates = [s for s in subway_stations[target_line] if s != current_station]
    if not candidates:
        candidates = [s for s in subway_stations[target_line]]
    return target_line, random.choice(candidates), app_type


def _gen_application_id(emp_id: str) -> str:
    suffix = "".join(random.choices(string.digits, k=6))
    return f"TA{emp_id[-4:]}{suffix}"[:16]


def _build_application(
    emp: dict[str, Any],
    current_line: str,
    current_station: str,
    today: date,
) -> dict[str, Any]:
    target_line, target_station, app_type = _pick_target_station(current_line, current_station)
    hire = _parse_date(emp["hire_date"])
    apply_start = max(hire + timedelta(days=180), today - timedelta(days=365))
    application_date = _random_date_between(apply_start, today - timedelta(days=1))

    expected_transfer_date = application_date + timedelta(days=random.randint(15, 60))
    urgency = random.choice(URGENCY_LEVELS) if random.random() < 0.2 else "普通"

    weights = [0.25, 0.45, 0.22, 0.08]
    approval_status = random.choices(APPROVAL_STATUSES, weights=weights, k=1)[0]

    approver_name = None
    approval_date = None
    approval_comment = None
    approval_days = None

    if approval_status == "待审批":
        pass
    elif approval_status == "已撤回":
        approval_comment = random.choice(["个人原因取消申请", "已与部门沟通暂不换站", "暂不换站"])
    else:
        approver_name = random.choice(APPROVERS)
        approval_date = _random_date_between(
            application_date + timedelta(days=1),
            min(today, application_date + timedelta(days=21)),
        )
        approval_days = (approval_date - application_date).days
        if approval_status == "已通过":
            approval_comment = random.choice(APPROVAL_COMMENTS_APPROVED)
        else:
            approval_comment = random.choice(APPROVAL_COMMENTS_REJECTED)

    return {
        "申请单号": _gen_application_id(emp["emp_id"]),
        "工号": emp["emp_id"],
        "姓名": emp["emp_name"],
        "部门": emp["department"],
        "岗位": emp["job_position"],
        "当前线路": current_line,
        "当前站点": current_station,
        "目标线路": target_line,
        "目标站点": target_station,
        "申请类型": app_type,
        "申请原因": random.choice(APPLICATION_REASONS),
        "申请日期": application_date.strftime("%Y-%m-%d"),
        "期望换站日期": expected_transfer_date.strftime("%Y-%m-%d"),
        "紧急程度": urgency,
        "审批状态": approval_status,
        "审批人": approver_name,
        "审批日期": approval_date.strftime("%Y-%m-%d") if approval_date else None,
        "审批意见": approval_comment,
        "审批耗时(天)": approval_days,
        "流程状态": PROCESS_STATUS_MAP[approval_status],
    }


def generate_transfer_applications(
    employees: list[dict[str, Any]],
    current_stations: dict[str, dict[str, str]],
    config: dict[str, Any],
) -> pd.DataFrame:
    today = date.today()
    target_count = int(config["application_count"])
    max_per_emp = int(config["max_applications_per_employee"])

    pool = list(employees)
    random.shuffle(pool)
    records: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for emp in pool:
        if len(records) >= target_count:
            break
        n_apps = random.randint(1, max_per_emp) if random.random() < 0.45 else 0
        if n_apps == 0:
            continue

        station_info = current_stations.get(emp["emp_id"])
        current_line = station_info["subway_line"] if station_info else emp["subway_line"]
        current_station = station_info["subway_station"] if station_info else emp["subway_station"]

        for _ in range(n_apps):
            if len(records) >= target_count:
                break
            rec = _build_application(emp, current_line, current_station, today)
            while rec["申请单号"] in used_ids:
                rec["申请单号"] = _gen_application_id(emp["emp_id"])
            used_ids.add(rec["申请单号"])
            records.append(rec)

    # 若随机抽样不足目标条数，继续补充
    idx = 0
    while len(records) < target_count:
        emp = pool[idx % len(pool)]
        station_info = current_stations.get(emp["emp_id"])
        current_line = station_info["subway_line"] if station_info else emp["subway_line"]
        current_station = station_info["subway_station"] if station_info else emp["subway_station"]
        rec = _build_application(emp, current_line, current_station, today)
        while rec["申请单号"] in used_ids:
            rec["申请单号"] = _gen_application_id(emp["emp_id"])
        used_ids.add(rec["申请单号"])
        records.append(rec)
        idx += 1

    return pd.DataFrame(records)


def prepare_rows(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"数据缺少字段: {missing}")
    prepared = df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)
    return [tuple(row) for row in prepared.itertuples(index=False, name=None)]


def ensure_application_table(cur: pymysql.cursors.Cursor, table_name: str) -> None:
    t = _quote_ident(table_name)
    cur.execute("SHOW TABLES LIKE %s", (table_name,))
    exists = cur.fetchone() is not None
    if exists:
        cur.execute(f"SHOW COLUMNS FROM {t} LIKE 'application_id'")
        if not cur.fetchone():
            cur.execute(f"DROP TABLE {t}")
            exists = False
    if not exists:
        cur.execute(create_application_table_sql(table_name))


def write_to_mysql(df: pd.DataFrame, config: dict[str, Any]) -> int:
    table_name = config["application_table"]
    rows = prepare_rows(df)
    t = _quote_ident(table_name)
    cols = ", ".join(_quote_ident(c) for c in INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    insert_sql = f"INSERT INTO {t} ({cols}) VALUES ({placeholders})"

    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            ensure_application_table(cur, table_name)
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


def print_summary(df: pd.DataFrame) -> None:
    print("=" * 80)
    print("换工作站点申请记录 - 数据概览")
    print("=" * 80)
    print(f"申请记录数: {len(df)}")
    print(f"涉及员工数: {df['工号'].nunique()}")
    print("\n前10条预览:")
    print(df.head(10).to_string(index=False))

    print("\n审批状态分布:")
    for s, cnt in df["审批状态"].value_counts().items():
        print(f"  {s}: {cnt}条")

    print("\n申请类型分布:")
    for t, cnt in df["申请类型"].value_counts().items():
        print(f"  {t}: {cnt}条")

    approved = df[df["审批状态"] == "已通过"]
    if len(approved) and approved["审批耗时(天)"].notna().any():
        print(f"\n已通过申请平均审批耗时: {approved['审批耗时(天)'].mean():.1f} 天")


def main() -> None:
    random.seed(42)
    config = load_db_config()

    employees = fetch_active_employees(config)
    current_stations = fetch_current_stations(config)
    df = generate_transfer_applications(employees, current_stations, config)
    print_summary(df)

    inserted = write_to_mysql(df, config)

    print("\n" + "=" * 80)
    print("换站申请数据已写入 MySQL")
    print(f"主机: {config['host']}:{config['port']}")
    print(f"库名: {config['database']}")
    print(f"申请记录表: {config['application_table']}")
    print(f"写入记录数: {inserted}")
    print("=" * 80)


if __name__ == "__main__":
    main()
