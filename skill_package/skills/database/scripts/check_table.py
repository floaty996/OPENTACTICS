from skill_package.core.registry import register_skill_tool
from skill_package.skills.database.db_client import describe_table

describe_schema = {
    "type": "function",
    "function": {
        "name": "describe_table",
        "description": "获取指定表的结构（字段、类型、是否可空、主键等）。须先 database_connect。",
        "parameters": {
            "type": "object",
            "properties": {
                "connection_id": {
                    "type": "string",
                    "description": "database_connect 返回的连接 id",
                },
                "table_name": {"type": "string", "description": "表名"},
            },
            "required": ["connection_id", "table_name"],
        },
    },
}


@register_skill_tool(
    "database",
    name="describe_table",
    schema=describe_schema,
    alias=["表结构", "字段说明"],
)
def describe_table_tool(connection_id: str, table_name: str) -> str:
    return describe_table(connection_id, table_name)
