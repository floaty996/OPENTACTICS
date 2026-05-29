"""
员工职称管理系统 - 数据库连接与配置
读取 workspace/{db_alias}/config.json 获取连接信息
"""
import json
import os
import pymysql

_CONFIG_CACHE = {}

def get_workspace_dir(db_alias: str) -> str:
    """获取工作区目录"""
    # 从环境变量或当前路径推算
    skill_package_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    workspace_dir = os.path.join(skill_package_dir, "workspace", db_alias)
    return workspace_dir

def load_config(db_alias: str) -> dict:
    """加载 workspace/{db_alias}/config.json"""
    cache_key = f"{db_alias}_config"
    if cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]
    
    workspace_dir = get_workspace_dir(db_alias)
    config_path = os.path.join(workspace_dir, "config.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    _CONFIG_CACHE[cache_key] = config
    return config

def get_source_conn(db_alias: str):
    """获取源库连接（只读）"""
    config = load_config(db_alias)
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config["user"],
        password=config.get("target_password") or config["password"],
        database=config["source_databases"][0],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

def get_target_conn(db_alias: str):
    """获取目标库连接（可写）"""
    config = load_config(db_alias)
    return pymysql.connect(
        host=config["host"],
        port=config["port"],
        user=config.get("target_user") or config["user"],
        password=config.get("target_password") or config["password"],
        database=config["target_database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )
