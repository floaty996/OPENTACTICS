"""
生成地铁工作人员模拟数据并写入 MySQL。

运行前：
  1. 复制 config/database.example.json 为 config/database.json
  2. 填写 host / user / password / database
  3. pip install pandas numpy pymysql
  4. python create_data.py
"""

from __future__ import annotations

import json
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pymysql

_ROOT = Path(__file__).resolve().parent
_CONFIG_PATH = _ROOT / "config" / "database.json"

TABLE_NAME_DEFAULT = "metro_employees"

COLUMN_MAP: dict[str, str] = {
    "工号": "emp_id",
    "姓名": "name",
    "身份证号": "id_card",
    "性别": "gender",
    "年龄": "age",
    "政治面貌": "political_status",
    "民族": "nationality",
    "所属线路": "subway_line",
    "所属站点": "subway_station",
    "部门": "department",
    "岗位": "job_position",
    "学历": "education",
    "职称": "professional_title",
    "职业资格": "qualification",
    "入职日期": "hire_date",
    "工龄": "seniority",
    "手机号": "phone",
    "月薪(元)": "monthly_salary",
    "当前状态": "status",
}

INSERT_COLUMNS = list(COLUMN_MAP.values())


def load_db_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到 {_CONFIG_PATH}，请先复制 config/database.example.json 并填写 MySQL 连接信息。"
        )
    with _CONFIG_PATH.open(encoding="utf-8") as f:
        config = json.load(f)

    config.setdefault("db_type", "mysql")
    config.setdefault("port", 3306)
    config.setdefault("table_name", TABLE_NAME_DEFAULT)
    config.setdefault("clear_before_insert", True)

    if config["db_type"].lower() != "mysql":
        raise ValueError("本脚本仅支持 MySQL，请将 db_type 设为 mysql。")

    for key in ("host", "user", "database"):
        if not config.get(key):
            raise ValueError(f"MySQL 配置缺少必填项: {key}")

    return config


def _quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def create_table_sql(table_name: str) -> str:
    t = _quote_ident(table_name)
    col_defs = """
    `emp_id` VARCHAR(8) NOT NULL,
    `name` VARCHAR(32) NOT NULL,
    `id_card` VARCHAR(18) NOT NULL,
    `gender` VARCHAR(4) NOT NULL,
    `age` INT NOT NULL,
    `political_status` VARCHAR(32) NOT NULL,
    `nationality` VARCHAR(32) NOT NULL,
    `subway_line` VARCHAR(16) NOT NULL,
    `subway_station` VARCHAR(64) NOT NULL,
    `department` VARCHAR(64) NOT NULL,
    `job_position` VARCHAR(64) NOT NULL,
    `education` VARCHAR(16) NOT NULL,
    `professional_title` VARCHAR(32) NOT NULL,
    `qualification` VARCHAR(64) NOT NULL,
    `hire_date` DATE NOT NULL,
    `seniority` INT NOT NULL,
    `phone` VARCHAR(16) NOT NULL,
    `monthly_salary` INT NOT NULL,
    `status` VARCHAR(16) NOT NULL,
    PRIMARY KEY (`emp_id`)
    """
    return (
        f"CREATE TABLE IF NOT EXISTS {t} ({col_defs}) "
        "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise ValueError(f"数据缺少字段: {missing}")
    return df[list(COLUMN_MAP.keys())].rename(columns=COLUMN_MAP)


def rows_from_dataframe(df: pd.DataFrame) -> list[tuple[Any, ...]]:
    prepared = prepare_dataframe(df)
    return [tuple(row) for row in prepared.itertuples(index=False, name=None)]


def connect_mysql(config: dict[str, Any]) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config.get("password", ""),
        database=config["database"],
        charset="utf8mb4",
        autocommit=False,
    )


def write_to_mysql(df: pd.DataFrame, config: dict[str, Any]) -> int:
    table_name = config["table_name"]
    rows = rows_from_dataframe(df)
    t = _quote_ident(table_name)
    cols = ", ".join(_quote_ident(c) for c in INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(INSERT_COLUMNS))
    insert_sql = f"INSERT INTO {t} ({cols}) VALUES ({placeholders})"

    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            cur.execute(create_table_sql(table_name))
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


# --- 数据生成 ---

np.random.seed(42)
random.seed(42)

subway_lines = ["1号线", "2号线", "3号线", "4号线", "5号线"]

subway_stations: dict[str, list[str]] = {}
for line in subway_lines:
    subway_stations[line] = [f"{line}{station}站" for station in range(1, 14)]

first_names = [
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "高",
]
last_names = [
    "伟", "芳", "娜", "敏", "静", "强", "磊", "洋", "杰", "娟",
    "涛", "明", "超", "燕", "丽", "丹", "文", "博", "华", "东",
]

departments = [
    "运营管理部", "站务部", "维修工程部", "安全监察部", "调度指挥中心",
    "客服中心", "人力资源部", "财务部", "技术部", "行政部",
]
positions = {
    "运营管理部": ["运营经理", "运营主管", "运营专员", "运营助理"],
    "站务部": ["站长", "副站长", "站务员", "票务员", "安检员"],
    "维修工程部": ["维修工程师", "维修技师", "电工", "机械师", "信号工"],
    "安全监察部": ["安全总监", "安全主管", "安全员", "监察员"],
    "调度指挥中心": ["调度长", "调度员", "监控员"],
    "客服中心": ["客服经理", "客服主管", "客服专员", "投诉处理员"],
    "人力资源部": ["HR经理", "招聘专员", "培训专员", "绩效专员"],
    "财务部": ["财务经理", "会计", "出纳", "财务专员"],
    "技术部": ["技术经理", "系统工程师", "网络工程师", "数据分析师"],
    "行政部": ["行政经理", "行政主管", "前台", "后勤专员"],
}

political_status = ["中共党员", "中共预备党员", "共青团员", "群众", "民主党派"]
nationalities = [
    "汉族", "满族", "回族", "壮族", "维吾尔族", "苗族", "彝族", "土家族", "藏族", "蒙古族",
]
education = ["高中", "中专", "大专", "本科", "硕士", "博士"]
professional_titles = ["无职称", "初级职称", "中级职称", "高级职称"]
qualifications = [
    "无", "电工证", "焊工证", "特种设备操作证", "消防工程师证",
    "安全工程师证", "会计师证", "人力资源管理师证", "计算机等级证书",
]


def generate_id() -> str:
    return "".join(random.choices(string.digits, k=8))


def generate_id_card() -> str:
    area_code = "".join(random.choices(string.digits, k=6))
    year = str(random.randint(1980, 2000))
    month = str(random.randint(1, 12)).zfill(2)
    day = str(random.randint(1, 28)).zfill(2)
    birth_date = f"{year}{month}{day}"
    seq_code = "".join(random.choices(string.digits, k=3))
    check_code = random.choice(list(string.digits) + ["X"])
    return f"{area_code}{birth_date}{seq_code}{check_code}"


def generate_name() -> str:
    return f"{random.choice(first_names)}{random.choice(last_names)}"


def generate_hire_date() -> str:
    start_date = datetime(2005, 1, 1)
    end_date = datetime(2024, 12, 31)
    random_days = random.randint(0, (end_date - start_date).days)
    return (start_date + timedelta(days=random_days)).strftime("%Y-%m-%d")


def generate_phone() -> str:
    return f"138{''.join(random.choices(string.digits, k=8))}"


def generate_employees(count: int = 1000) -> pd.DataFrame:
    employee_data: list[dict[str, Any]] = []
    current_year = 2024

    for _ in range(count):
        emp_id = generate_id()
        name = generate_name()
        id_card = generate_id_card()
        gender = random.choice(["男", "女"])
        age = current_year - int(id_card[6:10])
        line = random.choice(subway_lines)
        station = random.choice(subway_stations[line])
        department = random.choice(departments)
        position = random.choice(positions[department])
        hire_date = generate_hire_date()
        seniority = current_year - int(hire_date.split("-")[0])

        base_salary_map = {
            "经理": 8000, "主管": 6000, "专员": 4500, "助理": 3500,
            "站长": 7000, "副站长": 6000, "站务员": 4000, "票务员": 3800, "安检员": 3600,
            "工程师": 7500, "技师": 5500, "电工": 4800, "机械师": 5200, "信号工": 5000,
            "总监": 9000, "监察员": 5000, "调度长": 7200, "调度员": 5800, "监控员": 4200,
            "会计": 5000, "出纳": 4200, "前台": 3200, "后勤专员": 3400,
        }
        base_salary = 4500
        for key, value in base_salary_map.items():
            if key in position:
                base_salary = value
                break

        employee_data.append({
            "工号": emp_id,
            "姓名": name,
            "身份证号": id_card,
            "性别": gender,
            "年龄": age,
            "政治面貌": random.choice(political_status),
            "民族": random.choice(nationalities),
            "所属线路": line,
            "所属站点": station,
            "部门": department,
            "岗位": position,
            "学历": random.choice(education),
            "职称": random.choice(professional_titles),
            "职业资格": random.choice(qualifications),
            "入职日期": hire_date,
            "工龄": seniority,
            "手机号": generate_phone(),
            "月薪(元)": int(base_salary * (1 + 0.05 * seniority)),
            "当前状态": random.choice(["在职", "在职", "在职", "在职", "休假", "出差"]),
        })

    return pd.DataFrame(employee_data)


def print_summary(df: pd.DataFrame) -> None:
    print("=" * 80)
    print("地铁工作人员信息表（1000条记录）- 数据概览")
    print("=" * 80)
    print(f"数据规模: {df.shape[0]} 行 × {df.shape[1]} 列")
    print(df.head(10).to_string(index=False))


def main() -> None:
    config = load_db_config()
    df = generate_employees(1000)
    print_summary(df)

    inserted = write_to_mysql(df, config)

    print("\n" + "=" * 80)
    print("数据已写入 MySQL")
    print(f"主机: {config['host']}:{config['port']}")
    print(f"库名: {config['database']}")
    print(f"表名: {config['table_name']}")
    print(f"写入记录数: {inserted}")
    print("=" * 80)


if __name__ == "__main__":
    main()
