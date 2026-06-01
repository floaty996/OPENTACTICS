from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import connect, disconnect

connect_schema = {
    "type": "function",
    "function": {
        "name": "database_connect",
        "description": (
            "Connect to a database. source mode is read-only (documentation); "
            "target mode allows DDL/DML and must be config target_database. "
            "Prefer use_workspace_config=true to read workspace/{db_alias}/config.json."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "db_alias": {"type": "string", "description": "Workspace alias"},
                "db_type": {"type": "string", "enum": ["mysql", "postgresql", "sqlite"]},
                "connection_mode": {
                    "type": "string",
                    "enum": ["source", "target"],
                    "description": "source=read-only source DB; target=writable target DB",
                },
                "use_workspace_config": {
                    "type": "boolean",
                    "description": "When true, read host/user etc. from config.json",
                },
                "database": {
                    "type": "string",
                    "description": "Database name; source mode must be in source_databases; target mode may omit (uses target_database)",
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
        "description": "Disconnect a database session",
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
    alias=["connect_database", "customer_db_connect"],
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
    alias=["disconnect_database"],
)
def database_disconnect(connection_id: str) -> str:
    return disconnect(connection_id)
