from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import list_tables as _list_tables

list_tables_schema = {
    "type": "function",
    "function": {
        "name": "list_tables",
        "description": "列举当前连接数据库中的表名。须先 database_connect。",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "database_connect 返回的连接 id",
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
    alias=["列举表", "所有表"],
)
def list_tables(connection_id: str) -> str:
    return _list_tables(connection_id)
