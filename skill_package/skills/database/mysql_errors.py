"""将 pymysql / MySQL 连接异常转为用户可读的中文说明。"""

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
    将 (1049, "Unknown database 'xxx'") 等原始错误转为中文提示。

    role: 「源库」或「目标库」，用于保存配置时的连接测试。
    """
    errno, msg = _parse_mysql_errno_message(exc)
    db_name = _extract_db_name(msg, database)

    label = ""
    if role and db_name:
        label = f"{role}「{db_name}」"
    elif role:
        label = role
    elif db_name:
        label = f"数据库「{db_name}」"

    if errno == 1049 or "unknown database" in msg.lower():
        name = db_name or "（未识别库名）"
        who = label or f"数据库「{name}」"
        hint = "源数据库" if role == "源库" else "目标数据库" if role == "目标库" else "数据库"
        return (
            f"{who}在 MySQL 中不存在。"
            f"请检查「{hint}」名称是否填错（当前为 {name}），"
            f"或先在 MySQL 中手动创建该库（本系统不会自动建库）。"
        )

    if errno == 1045 or "access denied" in msg.lower():
        return (
            f"{label + ' ' if label else ''}MySQL 登录失败：用户名或密码不正确，"
            f"请核对账号密码及该用户是否允许从当前主机连接。"
        ).strip()

    if errno == 1044:
        name = db_name or _extract_db_name(msg, None) or "该库"
        return (
            f"账号无权访问数据库「{name}」。"
            f"请为 MySQL 用户授予该库的权限，或检查{('源库' if role == '源库' else '目标库') if role else '库名'}是否填错。"
        )

    if errno in (2002, 2003) or "can't connect" in msg.lower():
        return (
            "无法连接到 MySQL 服务器。请检查主机地址、端口是否正确，"
            "并确认 MySQL 服务已启动、防火墙未拦截。"
        )

    if errno == 2013 or "timed out" in msg.lower() or "timeout" in msg.lower():
        return "连接 MySQL 超时，请检查网络、主机地址与端口。"

    if label:
        return f"{label} 连接失败：{msg}"
    return f"数据库连接失败：{msg}"
