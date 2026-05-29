from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import connect, disconnect

connect_schema = {
    "type": "function",
    "function": {
        "name": "database_connect",
        "description": (
            "连接数据库。源库 source 仅只读（整理资料）；目标库 target 可建表/写入，且只能是 config 中的 target_database。"
            "推荐 use_workspace_config=true，从 workspace/{db_alias}/config.json 读取连接信息。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "工作区别名"},
                "db_type": {"type": "string", "enum": ["mysql", "postgresql", "sqlite"]},
                "connection_mode": {
                    "type": "string",
                    "enum": ["source", "target"],
                    "description": "source=源库只读；target=目标库可写",
                },
                "use_workspace_config": {
                    "type": "boolean",
                    "description": "true 时从 config.json 读取 host/user 等",
                },
                "database": {
                    "type": "string",
                    "description": "库名；source 模式须为 source_databases 之一；target 模式可省略（用 target_database）",
                },
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "user": {"type": "string"},
                "password": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["db_alias", "db_type"],
        },
    },
}

disconnect_schema = {
    "type": "function",
    "function": {
        "name": "database_disconnect",
        "description": "断开连接",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
            },
            "required": ["connection_id"],
        },
    },
}


@register_skill_tool(
    "database",
    name="database_connect",
    schema=connect_schema,
    alias=["连接数据库", "客户库连接"],
)
def database_connect(
    db_alias: str,
    db_type: str,
    connection_mode: str = "source",
    use_workspace_config: bool = False,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    file_path: str | None = None,
) -> str:
    return connect(
        db_alias=db_alias,
        db_type=db_type,
        connection_mode=connection_mode,
        use_workspace_config=use_workspace_config,
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        file_path=file_path,
    )


@register_skill_tool(
    "database",
    name="database_disconnect",
    schema=disconnect_schema,
    alias=["断开数据库"],
)
def database_disconnect(connection_id: str) -> str:
    return disconnect(connection_id)
