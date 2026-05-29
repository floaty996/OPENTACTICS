# 统一工作区

```
workspace/{db_alias}/
├── config.json      # MySQL：source_databases[] + target_database + 账号
├── dataset/         # database skill：只读整理产物（md）
├── frontend/        # UI_build：前端工程 + ui_knowledge.md（UI 知识）
├── backend/         # backend skill：REST API 工程 + api_knowledge.md
├── conversations/   # Skill Studio：对话记录（每会话一个 JSON）
└── manifest.json    # projects（前端）+ backend_projects（后端）
```

`conversations/{id}.json` 含 `title`、`messages`（user/assistant），由 Studio 自动写入。

## config.json 示例

```json
{
  "db_alias": "hr_project",
  "db_type": "mysql",
  "host": "127.0.0.1",
  "port": 3306,
  "user": "readonly_user",
  "password": "***",
  "source_databases": ["biz_db", "hr_legacy"],
  "target_database": "agent_workspace",
  "target_user": "agent_writer",
  "target_password": "***"
}
```

- **source_databases**：已有库，智能体只读探查、写入 dataset 文档。
- **target_database**：智能体唯一可 CREATE/INSERT 的库；建议单独 MySQL 账号授权。
