from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import describe_table

describe_schema = {
    "type": "function",
    "function": {
        "name": "describe_table",
        "description": "Get table structure (columns, types, nullability, keys). Requires database_connect first.",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "Connection id returned by database_connect",
                },
                "table_name": {"type": "string", "description": "Table name"},
            },
            "required": ["connection_id", "table_name"],
        },
    },
}


@register_skill_tool(
    "database",
    name="describe_table",
    schema=describe_schema,
    alias=["table_schema", "column_info"],
)
def describe_table_tool(connection_id: str, table_name: str) -> str:
    return describe_table(connection_id, table_name)
