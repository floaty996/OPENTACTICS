"""Convert pymysql / MySQL connection errors into readable English messages."""

from __future__ import annotations

import re

_UNKNOWN_DB_RE = re.compile(
    r"Unknown database ['\"](?P<name>[^'\"]+)['\"]",
    re.IGNORECASE,
)


def _parse_mysql_errno_message(exc: BaseException) -> tuple[int | None, str]:
    args = getattr(exc, "args", None)
    if args and len(args) >= 2 and isinstance(args[0], int):
        return args[0], str(args[1])
    return None, str(exc)


def _extract_db_name(msg: str, database: str | None) -> str:
    if database and database.strip():
        return database.strip()
    m = _UNKNOWN_DB_RE.search(msg)
    return m.group("name") if m else ""


def format_db_connection_error(
    exc: BaseException,
    *,
    database: str | None = None,
    role: str | None = None,
) -> str:
    """
    Turn errors like (1049, "Unknown database 'xxx'") into user-facing English.

    role: "source" or "target" for connection tests when saving config.
    """
    errno, msg = _parse_mysql_errno_message(exc)
    db_name = _extract_db_name(msg, database)

    label = ""
    if role and db_name:
        label = f'{role} database "{db_name}"'
    elif role:
        label = f"{role} database"
    elif db_name:
        label = f'database "{db_name}"'

    if errno == 1049 or "unknown database" in msg.lower():
        name = db_name or "(unknown name)"
        who = label or f'database "{name}"'
        hint = "source database" if role == "source" else "target database" if role == "target" else "database"
        return (
            f"{who} does not exist in MySQL. "
            f"Check whether the {hint} name is wrong (current: {name}), "
            f"or create the database manually in MySQL (this system does not auto-create databases)."
        )

    if errno == 1045 or "access denied" in msg.lower():
        return (
            f"{' ' + label if label else ''}MySQL login failed: incorrect username or password, "
            f"or the user is not allowed to connect from this host."
        ).strip()

    if errno == 1044:
        name = db_name or _extract_db_name(msg, None) or "that database"
        role_hint = "source" if role == "source" else "target" if role == "target" else "database"
        return (
            f'Account has no permission for database "{name}". '
            f"Grant privileges to the MySQL user, or verify the {role_hint} name."
        )

    if errno in (2002, 2003) or "can't connect" in msg.lower():
        return (
            "Cannot connect to MySQL server. Check host and port, "
            "ensure MySQL is running, and verify firewall rules."
        )

    if errno == 2013 or "timed out" in msg.lower() or "timeout" in msg.lower():
        return "MySQL connection timed out. Check network, host, and port."

    if label:
        return f"{label} connection failed: {msg}"
    return f"Database connection failed: {msg}"
