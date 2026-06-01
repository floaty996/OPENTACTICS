"""Multi-database connections and sessions; separate source (read-only) and target (writable)."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from skill_package.skills.database.mysql_errors import format_db_connection_error
from skill_package.workspace.config_loader import load_workspace_db_config

_SUPPORTED = frozenset({"mysql", "postgresql", "sqlite"})
_CONNECTION_MODES = frozenset({"source", "target"})

_READ_ONLY_RE = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|PRAGMA)\b",
    re.IGNORECASE | re.DOTALL,
)
_TARGET_ALLOWED_RE = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN|INSERT|UPDATE|DELETE|"
    r"CREATE|ALTER|DROP|TRUNCATE|REPLACE)\b",
    re.IGNORECASE | re.DOTALL,
)
_FORBIDDEN_RE = re.compile(
    r"\b(GRANT|REVOKE|MERGE|CALL|EXEC|EXECUTE|ATTACH|DETACH|COPY|LOAD)\b",
    re.IGNORECASE,
)
_USE_DB_RE = re.compile(r"^\s*USE\s+", re.IGNORECASE)


@dataclass
class DbSession:
    connection_id: str
    db_alias: str
    db_type: str
    database: str
    conn: Any
    connection_mode: str = "source"


_sessions: dict[str, DbSession] = {}


def _ok(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return _ok({"ok": False, "error": message})


def validate_sql_for_session(sql: str, connection_mode: str) -> None:
    stripped = sql.strip()
    if not stripped:
        raise ValueError("SQL cannot be empty.")
    if _FORBIDDEN_RE.search(stripped) or _USE_DB_RE.match(stripped):
        raise ValueError("GRANT/REVOKE/USE and other high-risk cross-database statements are not allowed.")

    if connection_mode == "source":
        if not _READ_ONLY_RE.match(stripped):
            raise ValueError("Source connections allow read-only SQL only (SELECT/SHOW/DESCRIBE/EXPLAIN/PRAGMA).")
        if re.search(
            r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE)\b",
            stripped,
            re.IGNORECASE,
        ):
            raise ValueError("Source DB forbids writes/DDL; use target connection (connection_mode=target).")
    else:
        if not _TARGET_ALLOWED_RE.match(stripped):
            raise ValueError(
                "Target DB allows SELECT/SHOW/DESCRIBE/INSERT/UPDATE/DELETE/CREATE/ALTER/DROP/TRUNCATE only."
            )


def validate_readonly_sql(sql: str) -> None:
    validate_sql_for_session(sql, "source")


def _resolve_credentials(
    *,
    db_alias: str,
    db_type: str,
    connection_mode: str,
    database: str | None,
    use_workspace_config: bool,
    host: str | None,
    port: int | None,
    user: str | None,
    password: str | None,
    file_path: str | None,
) -> tuple[str, str | None, int | None, str, str, str | None]:
    mode = connection_mode if connection_mode in _CONNECTION_MODES else "source"

    if use_workspace_config:
        cfg = load_workspace_db_config(db_alias)
        storage_mode = cfg.get("storage_mode") or "mysql"
        kind = cfg.get("db_type", db_type).strip().lower()
        # db_type in config may disagree with storage_mode (e.g. mis-set sqlite); trust storage_mode
        if storage_mode == "mysql":
            if mode == "target" and cfg.get("target_database"):
                kind = "mysql"
            elif mode == "source" and cfg.get("source_databases"):
                kind = "mysql"
        if mode == "target":
            if storage_mode == "local" or not cfg.get("target_database"):
                from skill_package.workspace.local_store import resolve_local_sqlite_path

                sqlite_path = resolve_local_sqlite_path(db_alias, rel_path=cfg.get("local_sqlite_path"))
                return "sqlite", None, None, "", "", sqlite_path.name, str(sqlite_path)
            db_name = cfg["target_database"]
            user = cfg.get("target_user") or cfg.get("user")
            password = cfg.get("target_password") or cfg.get("password")
            host = (cfg.get("host") or "").strip() or "127.0.0.1"
            port = cfg.get("port", 3306)
            file_path = cfg.get("file_path") if kind == "sqlite" else file_path
            return kind, host, port, user or "", password or "", db_name, file_path
        if not cfg.get("source_databases"):
            raise ValueError(
                "No source databases configured for this workspace; "
                "set source_databases or use connection_mode=target for the local DB."
            )
        if not database or not str(database).strip():
            raise ValueError(
                "When connecting to a source DB, database is required and must be in source_databases."
            )
        db_name = str(database).strip()
        if db_name not in cfg["source_databases"]:
            raise ValueError(
                f"database={db_name!r} is not in source_databases: {cfg['source_databases']}"
            )
        user = cfg.get("user")
        password = cfg.get("password")
        host = (cfg.get("host") or "").strip() or "127.0.0.1"
        port = cfg.get("port", 3306)
        file_path = cfg.get("file_path") if kind == "sqlite" else file_path
        return kind, host, port, user or "", password or "", db_name, file_path

    if not database or not str(database).strip():
        raise ValueError("Provide database or set use_workspace_config=true.")
    return (
        db_type.strip().lower(),
        host,
        port,
        user or "",
        password or "",
        str(database).strip(),
        file_path,
    )


def connect(
    *,
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
    alias = (db_alias or "").strip()
    if not alias:
        return _err("db_alias cannot be empty.")

    mode = connection_mode if connection_mode in _CONNECTION_MODES else "source"

    try:
        kind, host, port, user, password, db_name, file_path = _resolve_credentials(
            db_alias=alias,
            db_type=db_type,
            connection_mode=mode,
            database=database,
            use_workspace_config=use_workspace_config,
            host=host,
            port=port,
            user=user,
            password=password,
            file_path=file_path,
        )
    except (ValueError, FileNotFoundError) as e:
        return _err(str(e))

    if kind not in _SUPPORTED:
        return _err(f"Unsupported db_type: {db_type!r}")

    try:
        if kind == "sqlite":
            if not file_path or not str(file_path).strip():
                return _err("sqlite requires file_path.")
            path = str(file_path).strip()
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True) if mode == "source" else sqlite3.connect(path)
            db_name = path
        elif kind == "mysql":
            import pymysql

            if not all([host, user, db_name]):
                return _err("mysql requires host, user, and database.")
            conn = pymysql.connect(
                host=host,
                port=int(port or 3306),
                user=user,
                password=password or "",
                database=db_name,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                read_timeout=60,
                connect_timeout=15,
            )
        else:
            try:
                import psycopg2
            except ImportError:
                return _err("postgresql requires psycopg2-binary")

            if not all([host, user, db_name]):
                return _err("postgresql requires host, user, and database.")
            conn = psycopg2.connect(
                host=host,
                port=int(port or 5432),
                user=user,
                password=password or "",
                dbname=db_name,
                connect_timeout=15,
            )
            conn.autocommit = True

        cid = uuid.uuid4().hex[:12]
        _sessions[cid] = DbSession(
            connection_id=cid,
            db_alias=alias,
            db_type=kind,
            database=str(db_name),
            conn=conn,
            connection_mode=mode,
        )
        return _ok(
            {
                "ok": True,
                "connection_id": cid,
                "db_alias": alias,
                "db_type": kind,
                "database": db_name,
                "connection_mode": mode,
                "message": (
                    "Source DB connected (read-only)."
                    if mode == "source"
                    else "Target DB connected (writable; this database only)."
                ),
            }
        )
    except Exception as e:
        role = "source" if mode == "source" else "target"
        return _err(
            format_db_connection_error(e, database=str(db_name) if db_name else None, role=role)
        )


def disconnect(connection_id: str) -> str:
    sess = _sessions.pop(connection_id, None)
    if not sess:
        return _err(f"Invalid connection_id: {connection_id}")
    try:
        sess.conn.close()
    except Exception:
        pass
    return _ok({"ok": True, "connection_id": connection_id, "message": "Disconnected."})


def _get_session(connection_id: str) -> DbSession:
    sess = _sessions.get(connection_id)
    if not sess:
        raise ValueError(f"Invalid connection_id: {connection_id}. Call database_connect first.")
    return sess


def execute_query(connection_id: str, sql: str) -> str:
    sess = _get_session(connection_id)
    validate_sql_for_session(sql, sess.connection_mode)
    try:
        if sess.db_type == "sqlite":
            sess.conn.row_factory = sqlite3.Row
            cur = sess.conn.cursor()
            cur.execute(sql)
            if sql.strip().upper().startswith("SELECT") or "PRAGMA" in sql.upper()[:20]:
                rows = cur.fetchall()
                result = [dict(r) for r in rows]
            else:
                sess.conn.commit()
                result = [{"affected_rows": cur.rowcount}]
        elif sess.db_type == "mysql":
            with sess.conn.cursor() as cur:
                cur.execute(sql)
                if cur.description:
                    rows = cur.fetchall()
                    result = list(rows) if isinstance(rows, list) else []
                else:
                    sess.conn.commit()
                    result = [{"affected_rows": cur.rowcount}]
        else:
            from psycopg2.extras import RealDictCursor

            with sess.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql)
                if cur.description:
                    result = [dict(r) for r in cur.fetchall()]
                else:
                    result = [{"affected_rows": cur.rowcount}]

        truncated = False
        if len(result) > 200:
            result = result[:200]
            truncated = True
        return _ok(
            {
                "ok": True,
                "connection_id": connection_id,
                "db_alias": sess.db_alias,
                "database": sess.database,
                "connection_mode": sess.connection_mode,
                "row_count": len(result),
                "truncated": truncated,
                "rows": result,
            }
        )
    except Exception as e:
        return _err(f"Query failed: {e}")


def _quote_mysql_table(name: str) -> str:
    if not re.match(r"^[A-Za-z0-9_]+$", name):
        raise ValueError("Table name may contain letters, digits, and underscores only.")
    return f"`{name}`"


def describe_table(connection_id: str, table_name: str) -> str:
    sess = _get_session(connection_id)
    t = table_name.strip()
    if not t:
        return _err("table_name cannot be empty.")
    try:
        if sess.db_type == "sqlite":
            if not re.match(r"^[A-Za-z0-9_]+$", t):
                return _err("Table name may contain letters, digits, and underscores only.")
            cur = sess.conn.cursor()
            cur.execute("PRAGMA table_info(?)", (t,))
            rows = cur.fetchall()
            result = [
                {"name": r[1], "type": r[2], "notnull": bool(r[3]), "pk": bool(r[5])}
                for r in rows
            ]
        elif sess.db_type == "mysql":
            sql = f"DESCRIBE {_quote_mysql_table(t)}"
            return execute_query(connection_id, sql)
        else:
            sql = """
                SELECT column_name AS name, data_type AS type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                ORDER BY ordinal_position
            """
            from psycopg2.extras import RealDictCursor

            with sess.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, (t,))
                result = [dict(r) for r in cur.fetchall()]
        return _ok(
            {
                "ok": True,
                "connection_id": connection_id,
                "db_alias": sess.db_alias,
                "database": sess.database,
                "connection_mode": sess.connection_mode,
                "table_name": t,
                "columns": result,
            }
        )
    except Exception as e:
        return _err(f"Failed to describe table: {e}")


def list_tables(connection_id: str) -> str:
    sess = _get_session(connection_id)
    try:
        if sess.db_type == "sqlite":
            sql = "SELECT name AS table_name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        elif sess.db_type == "mysql":
            sql = "SHOW TABLES"
        else:
            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """
        raw = execute_query(connection_id, sql if sess.db_type != "postgresql" else sql.strip())
        data = json.loads(raw)
        if not data.get("ok"):
            return raw
        rows = data.get("rows", [])
        if sess.db_type == "mysql" and rows:
            key = next(iter(rows[0]))
            tables = [r[key] for r in rows]
        elif sess.db_type == "postgresql" and rows:
            tables = [r.get("table_name") for r in rows]
        else:
            tables = [r.get("table_name") for r in rows]
        return _ok(
            {
                "ok": True,
                "connection_id": connection_id,
                "db_alias": sess.db_alias,
                "database": sess.database,
                "connection_mode": sess.connection_mode,
                "tables": tables,
            }
        )
    except Exception as e:
        return _err(f"Failed to list tables: {e}")
