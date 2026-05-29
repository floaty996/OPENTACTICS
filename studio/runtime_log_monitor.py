"""从 saas 后端运行日志（.studio_uvicorn.log）中提取运行时错误。"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# uvicorn / starlette 访问日志：INFO 行里的 4xx/5xx（用户最常见「日志有红字」场景）
_ACCESS_LOG_RE = re.compile(
    r'"(?P<method>GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+'
    r'(?P<path>[^"]+)\s+HTTP/[\d.]+"\s+'
    r"(?P<status>\d{3})(?:\s+(?P<reason>[^\n]*))?",
    re.I,
)

# 单行应用日志中的明显错误
_ERROR_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(ERROR|CRITICAL)\b", re.I),
    re.compile(
        r"\b(ModuleNotFoundError|ImportError|SyntaxError|"
        r"ConnectionRefusedError|OperationalError|"
        r"ProgrammingError|IntegrityError)\b"
    ),
    re.compile(r"pymysql\.err\.", re.I),
    re.compile(r"sqlalchemy\.exc\.", re.I),
    re.compile(r"Application startup failed", re.I),
    re.compile(r"Failed to connect", re.I),
    re.compile(r"Exception in ASGI application", re.I),
    re.compile(r"\b500 Internal Server Error\b", re.I),
)

# 排除误报（含 ERROR 子串但非异常）；访问日志 4xx/5xx 不走此过滤
_NOISE_LINE_RE = re.compile(
    r"(log level|logging\.|\[info\])",
    re.I,
)

_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\)", re.I)
_EXCEPTION_TAIL = re.compile(
    r"^[\w.]*(Error|Exception)(:\s*.+)?$",
)


def _error_id(backend_key: str, text: str) -> str:
    digest = hashlib.sha256(f"{backend_key}\n{text.strip()}".encode()).hexdigest()
    return digest[:16]


def _http_access_error_from_line(line: str) -> dict[str, str] | None:
    m = _ACCESS_LOG_RE.search(line)
    if not m:
        return None
    status = int(m.group("status"))
    if status < 400:
        return None
    method = m.group("method").upper()
    path = m.group("path").strip()
    reason = (m.group("reason") or "").strip()
    title = f"{method} {path} → {status}"
    if reason:
        title += f" {reason}"
    excerpt = line.strip()
    return {"title": title[:200], "excerpt": excerpt}


def _line_looks_like_error(line: str) -> bool:
    if _http_access_error_from_line(line):
        return True
    s = line.strip()
    if not s:
        return False
    if s.startswith("INFO:") or s.startswith("WARNING:"):
        return False
    if _NOISE_LINE_RE.search(s):
        return False
    return any(p.search(s) for p in _ERROR_LINE_PATTERNS)


def _extract_traceback_blocks(lines: list[str]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if not _TRACEBACK_START.match(lines[i].strip()):
            i += 1
            continue
        start = i
        block = [lines[i]]
        i += 1
        while i < len(lines):
            block.append(lines[i])
            if _EXCEPTION_TAIL.match(lines[i].strip()):
                i += 1
                break
            # 空行结束 traceback
            if not lines[i].strip() and len(block) > 3:
                i += 1
                break
            i += 1
        text = "\n".join(block).strip()
        if len(text) > 20:
            blocks.append((start + 1, text))
    return blocks


def _title_from_block(text: str) -> str:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if _EXCEPTION_TAIL.match(line):
            return line[:200]
        if line and not line.startswith("File "):
            return line[:200]
    first = text.splitlines()[0].strip() if text else "运行时错误"
    return first[:200]


def _http_access_dedupe_key(line: str) -> str | None:
    m = _ACCESS_LOG_RE.search(line)
    if not m or int(m.group("status")) < 400:
        return None
    return f"{m.group('method').upper()}|{m.group('path').strip()}|{m.group('status')}"


def scan_runtime_errors_chunk(
    backend_key: str,
    chunk: str,
    start_byte: int,
    *,
    max_errors: int = 32,
) -> list[dict[str, Any]]:
    """扫描日志增量片段；每条 4xx/5xx 按文件字节偏移生成唯一 id（重复点击会出新提醒）。"""
    if not chunk or not chunk.strip():
        return []

    out: list[dict[str, Any]] = []
    http_keys_seen: set[str] = set()
    byte_pos = start_byte
    for line in chunk.splitlines():
        line_b = line.encode("utf-8", errors="replace")
        access = _http_access_error_from_line(line)
        if access:
            http_key = _http_access_dedupe_key(line)
            if http_key and http_key in http_keys_seen:
                byte_pos += len(line_b) + 1
                continue
            if http_key:
                http_keys_seen.add(http_key)
            excerpt = line.strip()
            eid = _error_id(backend_key, f"@{byte_pos}:{excerpt}")
            out.append(
                {
                    "id": eid,
                    "kind": "http",
                    "title": access["title"],
                    "excerpt": excerpt,
                    "byte_offset": byte_pos,
                }
            )
            if len(out) >= max_errors:
                return out
        elif _line_looks_like_error(line):
            excerpt = line.strip()
            eid = _error_id(backend_key, f"@{byte_pos}:{excerpt}")
            out.append(
                {
                    "id": eid,
                    "kind": "line",
                    "title": excerpt[:200],
                    "excerpt": excerpt,
                    "byte_offset": byte_pos,
                }
            )
            if len(out) >= max_errors:
                return out
        byte_pos += len(line_b) + 1

    # traceback 跨行：在 chunk 内用通用扫描补全（HTTP 访问日志已在上面按行处理，勿重复）
    for item in scan_runtime_errors(backend_key, chunk, max_errors=max_errors):
        if item.get("kind") != "traceback":
            continue
        tb_id = item.get("id")
        if tb_id and not any(x.get("id") == tb_id for x in out):
            item = {**item, "id": _error_id(backend_key, f"@{start_byte}:tb:{tb_id}")}
            out.append(item)
            if len(out) >= max_errors:
                break
    return out


def scan_runtime_errors(
    backend_key: str,
    log_content: str,
    *,
    max_errors: int = 8,
) -> list[dict[str, Any]]:
    """从日志文本提取错误条目（按出现顺序，去重）。"""
    if not log_content or not log_content.strip():
        return []

    lines = log_content.splitlines()
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    for line_no, block in _extract_traceback_blocks(lines):
        eid = _error_id(backend_key, block)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        out.append(
            {
                "id": eid,
                "kind": "traceback",
                "title": _title_from_block(block),
                "excerpt": block[-4000:] if len(block) > 4000 else block,
                "line": line_no,
            }
        )
        if len(out) >= max_errors:
            return out

    # 访问日志 4xx/5xx：按 method+path+status 去重，保留最近一次行号
    access_latest: dict[str, tuple[int, str, dict[str, str]]] = {}

    for i, line in enumerate(lines):
        access = _http_access_error_from_line(line)
        if access:
            m = _ACCESS_LOG_RE.search(line)
            if m:
                key = f"{m.group('method').upper()}|{m.group('path').strip()}|{m.group('status')}"
                access_latest[key] = (i + 1, line, access)
            continue
        if not _line_looks_like_error(line):
            continue
        block = line.strip()
        eid = _error_id(backend_key, block)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        j = i + 1
        extra: list[str] = []
        while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t")):
            extra.append(lines[j])
            j += 1
            if len(extra) >= 12:
                break
        if extra:
            block = "\n".join([block, *extra])
        out.append(
            {
                "id": eid,
                "kind": "line",
                "title": block.splitlines()[0][:200],
                "excerpt": block[-2000:] if len(block) > 2000 else block,
                "line": i + 1,
            }
        )
        if len(out) >= max_errors:
            return out

    for _line_no, raw_line, access in access_latest.values():
        block = access["excerpt"]
        eid = _error_id(backend_key, f"http:{access['title']}")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        out.append(
            {
                "id": eid,
                "kind": "http",
                "title": access["title"],
                "excerpt": block[-2000:] if len(block) > 2000 else block,
                "line": _line_no,
            }
        )
        if len(out) >= max_errors:
            break

    return out
