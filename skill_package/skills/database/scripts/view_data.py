from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import execute_query

query_schema = {
    "type": "function",
    "function": {
        "name": "database_query",
        "description": (
            "执行 SQL。源库连接仅只读；目标库连接可 CREATE/INSERT 等（仅限 target_database）。"
            "须先 database_connect(connection_mode=source|target)。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "database_connect 返回的连接 id",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL 语句",
                },
            },
            "required": ["connection_id", "sql"],
        },
    },
}


@register_skill_tool(
    "database",
    name="database_query",
    schema=query_schema,
    alias=["查数据库", "执行SQL", "数据库查询"],
)
def database_query(connection_id: str, sql: str) -> str:
    return execute_query(connection_id, sql)
