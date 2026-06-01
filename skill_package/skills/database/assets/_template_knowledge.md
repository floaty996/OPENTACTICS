---
db_alias: "{customer_db_alias}"
generated_at: "{YYYY-MM-DD}"
scope: "{scope, e.g. full order domain / 5 user-related tables}"
business_goal: "{user business goal, verbatim or summary}"
---

# {Topic title}

## 1. Business context and goals

- **Business scenario**:
- **Questions to answer this pass**:
- **Out of scope**:

## 2. Core entities and table mapping

| Business entity | Primary table | Notes |
|-----------------|---------------|-------|
| e.g. User | users | Account master data |

## 3. Table structure summary

### 3.1 `{table_name}`

| Column | Type | Nullable | Key | Business meaning |
|--------|------|----------|-----|------------------|
| id | bigint | N | PK | Primary key |

**Sample observations** (redacted): …

## 4. Data relationships

### 4.1 Relationship overview

| From table | From column | To table | To column | Cardinality | Evidence |
|------------|-------------|----------|-----------|-------------|----------|
| orders | user_id | users | id | N:1 | naming + samples |

### 4.2 ER diagram (Mermaid)

```mermaid
erDiagram
  USERS ||--o{ ORDERS : places
  USERS {
    bigint id PK
    string email
  }
  ORDERS {
    bigint id PK
    bigint user_id FK
  }
```

## 5. Key business rules (inferred from schema)

- …

## 6. Open questions / risks

- Implied relations without FK: …
- Enum/status meanings not documented in DB: …

## 7. Appendix

- **Connection info**: `db_alias` / `db_type` / `database` (no passwords)
- **Tables analyzed**:
- **Tables not covered**:
