from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import execute_query

query_schema = {
    "type": "function",
    "function": {
        "name": "database_query",
        "description": (
            "Execute SQL. Source connections are read-only; target connections allow CREATE/INSERT etc. "
            "(target_database only). Requires database_connect(connection_mode=source|target) first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "Connection id returned by database_connect",
                },
                "sql": {
                    "type": "string",
                    "description": "SQL statement",
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
    alias=["query_database", "execute_sql"],
)
def database_query(connection_id: str, sql: str) -> str:
    return execute_query(connection_id, sql)
