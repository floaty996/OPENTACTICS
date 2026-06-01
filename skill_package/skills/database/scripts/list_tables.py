from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import list_tables as _list_tables

list_tables_schema = {
    "type": "function",
    "function": {
        "name": "list_tables",
        "description": "List table names in the connected database. Requires database_connect first.",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "Connection id returned by database_connect",
                },
            },
            "required": ["connection_id"],
        },
    },
}


@register_skill_tool(
    "database",
    name="list_tables",
    schema=list_tables_schema,
    alias=["list_all_tables"],
)
def list_tables(connection_id: str) -> str:
    return _list_tables(connection_id)
