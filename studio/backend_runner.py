"""Studio 系统预览：自动启动 workspace 内 FastAPI 后端（端口冲突时自动换端口）。"""

from __future__ import annotations

import atexit
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skill_package.skills.backend.scripts.backend_assets import (
    _project_root as backend_project_root,
    _read_manifest_file,
    _scan_projects as scan_backend_projects,
)
from skill_package.workspace.paths import config_path, validate_db_alias

_API_BASE_RE = re.compile(
    r"(?:var|const|let)\s+API_BASE\s*=\s*['\"][^'\"]*['\"]\s*;?",
    re.I,
)
_API_VAR_RE = re.compile(
    r"(?:var|const|let)\s+API\s*=\s*['\"][^'\"]*['\"]\s*;?",
    re.I,
)
_ROUTER_DECORATOR_RE = re.compile(
    r"@(?:app|[\w_]+)\.(?:get|post|put|delete|patch|head|options)\(\s*[\"']([^\"']+)[\"']",
    re.I,
)
_PORT_RANGE = range(8000, 8100)
_PORT_WAIT_TIMEOUT_S = 25.0
_PORT_WAIT_INTERVAL_S = 0.25
_PIP_MARKER = ".studio_pip_done"


@dataclass
class _BackendProc:
    db_alias: str
    project_name: str
    port: int
    api_prefix: str
    process: subprocess.Popen[Any]
    log_path: Path


_REGISTRY: dict[str, _BackendProc] = {}
# 日志增量读取偏移（用于检测「新出现的」错误）
_LOG_WATCH_OFFSET: dict[str, int] = {}


def reset_runtime_log_watch(db_alias: str, project_name: str) -> None:
    _LOG_WATCH_OFFSET.pop(_registry_key(db_alias, project_name), None)


def _registry_key(db_alias: str, project_name: str) -> str:
    return f"{validate_db_alias(db_alias)}::{project_name}"


def inject_studio_api_base(html: str, api_base: str) -> str:
    """向 preview.html 注入运行时 API 基址（仅设置 __STUDIO_API_BASE__，生成规范由 skill FULLSTACK_API 块负责）。"""
    import json as _json

    base = api_base.rstrip("/")
    base_js = _json.dumps(base)
    studio_boot = (
        f"<script>window.__STUDIO_PREVIEW__=true;window.__STUDIO_API_BASE__={base_js};</script>\n"
        "<script>(function(){"
        "if(window.__STUDIO_FETCH_HOOK__)return;window.__STUDIO_FETCH_HOOK__=true;"
        "function reportHttpError(url,status,detail){try{"
        "window.parent.postMessage({type:'studio-preview-http-error',url:String(url||''),"
        "status:Number(status)||0,detail:String(detail||''),ts:Date.now()},'*');"
        "}catch(e){}}"
        "var orig=window.fetch;"
        "window.fetch=function(){var args=arguments;"
        "return orig.apply(this,args).then(function(res){"
        "if(res&&(!res.ok||(res.status>=400))){"
        "reportHttpError(res.url||args[0],res.status,'HTTP '+res.status);"
        "}return res;}).catch(function(err){"
        "reportHttpError(args[0],0,String(err&&err.message||err));throw err;});};"
        "window.addEventListener('unhandledrejection',function(ev){"
        "var r=ev&&ev.reason;reportHttpError(location.href,0,String(r&&r.message||r));"
        "});"
        "})();</script>\n"
    )
    if re.search(r"<head[^>]*>", html, re.I):
        html = re.sub(
            r"(<head[^>]*>)",
            lambda m: m.group(1) + "\n" + studio_boot,
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = studio_boot + html
    return html


def _http_get_status(url: str, *, timeout: float = 1.5) -> int | None:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception:
        return None


def _route_paths_from_main(main_py: Path) -> list[str]:
    """从 main.py 提取可用于探测的 GET 路径（含 APIRouter 装饰器）。"""
    try:
        text = main_py.read_text(encoding="utf-8")
    except OSError:
        return []
    paths = list(dict.fromkeys(_ROUTER_DECORATOR_RE.findall(text)))
    preferred = (
        "/statistics/overview",
        "/api/statistics/overview",
        "/api/health",
        "/health",
        "/employees",
        "/api/employees",
        "/stations",
        "/openapi.json",
    )
    ordered: list[str] = [p for p in preferred if p in paths]
    for p in paths:
        if p not in ordered and "{" not in p:
            ordered.append(p)
    if "/openapi.json" not in ordered:
        ordered.append("/openapi.json")
    return ordered[:12]


def _openapi_paths_from_port(port: int) -> list[str]:
    """从运行中后端的 openapi.json 读取路径列表。"""
    host = f"http://127.0.0.1:{port}"
    for url in (f"{host}/openapi.json",):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        raw_paths = list((data.get("paths") or {}).keys())
        if not raw_paths:
            continue
        preferred = (
            "/api/health",
            "/health",
            "/statistics/overview",
            "/api/statistics/overview",
            "/employees",
            "/api/employees",
            "/stations",
        )
        ordered = [p for p in preferred if p in raw_paths]
        for p in raw_paths:
            if p not in ordered and "{" not in p:
                ordered.append(p)
        return ordered[:16]
    return []


def detect_api_base_url(
    port: int,
    proj_dir: Path,
    *,
    manifest_api_prefix: str = "/api",
) -> str:
    """探测后端真实 API 基址（manifest 的 api_prefix 常与 main.py 不一致）。"""
    host = f"http://127.0.0.1:{port}"
    main_py = proj_dir / "main.py"
    paths = _openapi_paths_from_port(port)
    if not paths:
        paths = _route_paths_from_main(main_py) if main_py.is_file() else ["/openapi.json"]
    manifest_prefix = (manifest_api_prefix or "/api").rstrip("/")

    for path in paths:
        direct = f"{host}{path}"
        status = _http_get_status(direct)
        if status is not None and status < 400:
            if path.startswith("/api/") or path == "/api":
                return f"{host}/api".rstrip("/")
            if manifest_prefix and path.startswith(f"{manifest_prefix}/"):
                return f"{host}{manifest_prefix}".rstrip("/")
            return host.rstrip("/")
        if manifest_prefix and not path.startswith(manifest_prefix):
            prefixed = f"{host}{manifest_prefix}{path}"
            status = _http_get_status(prefixed)
            if status is not None and status < 400:
                return f"{host}{manifest_prefix}".rstrip("/")

    for path in ("/api/health", "/health", "/openapi.json"):
        direct = f"{host}{path}"
        status = _http_get_status(direct)
        if status is not None and status < 400:
            if path.startswith("/api/"):
                return f"{host}/api".rstrip("/")
            return host.rstrip("/")

    if manifest_prefix:
        return f"{host}{manifest_prefix}".rstrip("/")
    return host.rstrip("/")


def _api_path_suffix(api_base_url: str, port: int) -> str:
    base = api_base_url.rstrip("/")
    host = f"http://127.0.0.1:{port}"
    if base == host.rstrip("/"):
        return ""
    if base.startswith(host):
        return base[len(host) :] or ""
    return ""


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.4)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def _wait_port_open(port: int) -> bool:
    """仅检测端口是否开始监听，不请求业务 HTTP 接口。"""
    deadline = time.time() + _PORT_WAIT_TIMEOUT_S
    while time.time() < deadline:
        if _is_port_open("127.0.0.1", port):
            return True
        time.sleep(_PORT_WAIT_INTERVAL_S)
    return False


def _listening_pids_on_port(port: int) -> list[int]:
    """仅返回在 port 上 LISTEN 的 PID，不包含连到该端口的客户端（Studio 健康检查会误命中）。"""
    studio_pid = os.getpid()
    pids: list[int] = []
    try:
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if not line.isdigit():
                    continue
                pid = int(line)
                if pid != studio_pid:
                    pids.append(pid)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return pids


def _terminate_port_listeners(port: int) -> None:
    """释放端口：只结束监听该端口的进程，绝不 kill 连到该端口的客户端（含 Studio 自身）。"""
    pids = _listening_pids_on_port(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    if pids:
        time.sleep(0.35)


def _port_candidates(preferred: int) -> list[int]:
    preferred = int(preferred or 8000)
    return [preferred] + [p for p in _PORT_RANGE if p != preferred]


def _log_shows_bind_failure(log_path: Path) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "address already in use" in text or "Errno 48" in text


def _log_shows_startup_failure(log_path: Path) -> bool:
    """进程已退出且日志含 Traceback / 导入错误等，说明不是端口问题而是应用起不来。"""
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    if "Traceback (most recent call last)" in text:
        return True
    if "Error while loading" in text or "ModuleNotFoundError" in text:
        return True
    if "NameError:" in text or "SyntaxError:" in text or "ImportError:" in text:
        return True
    return False


def _resolve_backend_for_frontend(
    db_alias: str, frontend_project: str | None, backend_project: str | None
) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    backends = [b for b in scan_backend_projects(alias) if b.get("db_alias") == alias]
    if not backends:
        raise FileNotFoundError(f"工作区 {alias} 下没有 backend 工程，请先用 backend skill 创建 API。")

    if backend_project:
        match = next((b for b in backends if b["project_name"] == backend_project), None)
        if not match:
            raise FileNotFoundError(f"后端工程不存在: {backend_project}")
        return match

    if frontend_project:
        match = next(
            (b for b in backends if b.get("linked_frontend") == frontend_project),
            None,
        )
        if not match:
            match = next(
                (b for b in backends if b["project_name"] == frontend_project),
                None,
            )
        if not match and len(backends) == 1:
            match = backends[0]
        if not match:
            raise FileNotFoundError(
                f"未找到与前端「{frontend_project}」关联的后端，请在 api_manifest.json 设置 linked_frontend。"
            )
        return match

    return backends[0]


def _ensure_pip(proj_dir: Path) -> None:
    marker = proj_dir / _PIP_MARKER
    req = proj_dir / "requirements.txt"
    if marker.is_file() or not req.is_file():
        if req.is_file():
            marker.write_text("ok", encoding="utf-8")
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req)],
        cwd=str(proj_dir),
        check=True,
        capture_output=True,
        timeout=180,
    )
    marker.write_text("ok", encoding="utf-8")


def _stop_registered(key: str) -> None:
    proc = _REGISTRY.pop(key, None)
    if not proc:
        return
    try:
        proc.process.terminate()
        proc.process.wait(timeout=5)
    except Exception:
        try:
            proc.process.kill()
        except Exception:
            pass


def restart_backend_running(
    db_alias: str,
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    """停止 Studio 托管的后端进程（及占用端口的残留）后重新启动。"""
    row = _resolve_backend_for_frontend(db_alias, frontend_project, backend_project)
    project_name = row["project_name"]
    key = _registry_key(db_alias, project_name)
    proj_dir = backend_project_root(db_alias, project_name)
    meta = _read_manifest_file(proj_dir) or {}
    preferred_port = int(meta.get("default_port") or 8000)

    ports_to_clear: set[int] = {preferred_port}
    existing = _REGISTRY.get(key)
    if existing:
        ports_to_clear.add(existing.port)
    _stop_registered(key)
    reset_runtime_log_watch(validate_db_alias(db_alias), project_name)
    time.sleep(0.3)
    for port in ports_to_clear:
        if _is_port_open("127.0.0.1", port):
            _terminate_port_listeners(port)
    time.sleep(0.25)

    result = ensure_backend_running(
        db_alias,
        frontend_project=frontend_project,
        backend_project=backend_project,
    )
    port = int(result["port"])
    msg = f"已重启后端 backend/{project_name}（端口 {port}"
    if port != preferred_port:
        msg += f"，原配置端口 {preferred_port} 已被占用"
    msg += "）"
    result["restarted"] = True
    result["started"] = True
    result["message"] = msg
    return result


def ensure_backend_running(
    db_alias: str,
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
) -> dict[str, Any]:
    """启动或复用后端进程，返回实际 api_base_url。"""
    row = _resolve_backend_for_frontend(db_alias, frontend_project, backend_project)
    project_name = row["project_name"]
    key = _registry_key(db_alias, project_name)
    proj_dir = backend_project_root(db_alias, project_name)
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"后端目录不存在: backend/{project_name}/")
    main_py = proj_dir / "main.py"
    if not main_py.is_file():
        raise FileNotFoundError(f"backend/{project_name}/ 缺少 main.py")

    meta = _read_manifest_file(proj_dir) or {}
    api_prefix = str(meta.get("api_prefix") or "/api")
    preferred_port = int(meta.get("default_port") or 8000)

    existing = _REGISTRY.get(key)
    if existing and existing.process.poll() is None:
        if _is_port_open("127.0.0.1", existing.port):
            detected = detect_api_base_url(
                existing.port, proj_dir, manifest_api_prefix=api_prefix
            )
            existing.api_prefix = _api_path_suffix(detected, existing.port)
            return _result_payload(
                db_alias,
                project_name,
                existing.port,
                detected,
                started=False,
                message="后端已在运行（Studio 本次会话启动）",
            )
        _stop_registered(key)

    cfg_file = config_path(validate_db_alias(db_alias))
    if not cfg_file.is_file():
        raise FileNotFoundError(
            f"工作区缺少数据库配置 {cfg_file.name}，请先在 Studio 完成初始化。"
        )
    env = {
        **dict(__import__("os").environ),
        "PYTHONUNBUFFERED": "1",
        "STUDIO_WORKSPACE_CONFIG": str(cfg_file.resolve()),
        "STUDIO_DB_ALIAS": validate_db_alias(db_alias),
    }
    try:
        cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        if isinstance(cfg_data, dict):
            storage_mode = str(
                cfg_data.get("storage_mode")
                or ("mysql" if cfg_data.get("target_database") else "local")
            )
            env["STUDIO_STORAGE_MODE"] = storage_mode
            if storage_mode == "local":
                from skill_package.workspace.local_store import resolve_local_sqlite_path

                sqlite_path = resolve_local_sqlite_path(
                    validate_db_alias(db_alias),
                    rel_path=str(cfg_data.get("local_sqlite_path") or "data/app.db"),
                )
                env["STUDIO_LOCAL_SQLITE"] = str(sqlite_path.resolve())
            pwd = str(cfg_data.get("password") or "").strip()
            if pwd and pwd != "***":
                env["DB_PASSWORD"] = pwd
            tgt = str(cfg_data.get("target_password") or "").strip()
            if tgt and tgt != "***":
                env["DB_TARGET_PASSWORD"] = tgt
    except (json.JSONDecodeError, OSError):
        pass

    try:
        _ensure_pip(proj_dir)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"安装后端依赖失败（pip install）。{err}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("安装后端依赖超时，请在本机手动 pip install -r requirements.txt") from e

    log_path = proj_dir / ".studio_uvicorn.log"
    last_tail = ""
    started_port: int | None = None

    # 释放首选端口上的残留进程（常见于上次 Studio/uvicorn 未正常退出）
    if _is_port_open("127.0.0.1", preferred_port):
        _terminate_port_listeners(preferred_port)
        time.sleep(0.25)

    for port in _port_candidates(preferred_port):
        log_path.write_text("", encoding="utf-8")
        reset_runtime_log_watch(validate_db_alias(db_alias), project_name)
        log_f = open(log_path, "a", encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(proj_dir),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
        )
        log_f.close()
        time.sleep(0.35)

        if proc.poll() is not None:
            last_tail = log_path.read_text(encoding="utf-8")[-2000:]
            if _log_shows_bind_failure(log_path):
                continue
            if _log_shows_startup_failure(log_path):
                raise RuntimeError(
                    f"后端启动失败（应用代码或依赖错误），请打开「后端日志」或检查 backend/{project_name}/main.py。"
                    + (f"\n日志末尾:\n{last_tail}" if last_tail else "")
                )
            continue

        if proc.poll() is None and _wait_port_open(port):
            detected_base = detect_api_base_url(
                port, proj_dir, manifest_api_prefix=api_prefix
            )
            _REGISTRY[key] = _BackendProc(
                db_alias=validate_db_alias(db_alias),
                project_name=project_name,
                port=port,
                api_prefix=_api_path_suffix(detected_base, port),
                process=proc,
                log_path=log_path,
            )
            started_port = port
            break

        _REGISTRY.pop(key, None)
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        last_tail = log_path.read_text(encoding="utf-8")[-2000:]
        _stop_registered(key)
        if _is_port_open("127.0.0.1", port):
            _terminate_port_listeners(port)

    if started_port is None:
        raise RuntimeError(
            f"后端在 8000–8099 内均未能成功启动。请检查 backend/{project_name}/ 依赖与数据库配置。"
            + (f"\n日志末尾:\n{last_tail}" if last_tail else "")
        )

    port = started_port
    proc = _REGISTRY[key]
    host = f"http://127.0.0.1:{port}".rstrip("/")
    suffix = (proc.api_prefix or "").rstrip("/")
    detected_base = f"{host}{suffix}" if suffix else host
    msg = f"已启动后端 backend/{project_name}（端口 {port}"
    if port != preferred_port:
        msg += f"，原配置端口 {preferred_port} 已被占用"
    msg += "）"
    return _result_payload(
        db_alias, project_name, port, detected_base, started=True, message=msg
    )


def _result_payload(
    db_alias: str,
    project_name: str,
    port: int,
    api_base_url: str,
    *,
    started: bool,
    message: str,
) -> dict[str, Any]:
    base = api_base_url.rstrip("/")
    suffix = _api_path_suffix(base, port) or ""
    return {
        "ok": True,
        "db_alias": db_alias,
        "backend_project": project_name,
        "port": port,
        "api_prefix": suffix,
        "api_base_url": base,
        "running": True,
        "started": started,
        "message": message,
    }


def _tail_text_file(path: Path, *, max_lines: int = 500, max_bytes: int = 512_000) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    return "\n".join(lines), truncated


def read_backend_log(
    db_alias: str,
    *,
    frontend_project: str | None = None,
    backend_project: str | None = None,
    tail_lines: int = 500,
    reset_watch: bool = False,
) -> dict[str, Any]:
    """读取 workspace 后端工程的 Studio uvicorn 日志（.studio_uvicorn.log）。"""
    row = _resolve_backend_for_frontend(db_alias, frontend_project, backend_project)
    project_name = row["project_name"]
    alias = validate_db_alias(db_alias)
    if reset_watch:
        reset_runtime_log_watch(alias, project_name)
    proj_dir = backend_project_root(db_alias, project_name)
    log_path = proj_dir / ".studio_uvicorn.log"
    rel_log = f"backend/{project_name}/.studio_uvicorn.log"
    max_lines = max(50, min(int(tail_lines or 500), 5000))
    content, truncated = _tail_text_file(log_path, max_lines=max_lines)
    runtime = get_backend_runtime(db_alias, project_name)
    backend_key = _registry_key(alias, project_name)
    log_text = content if content else ""
    runtime_errors, new_runtime_errors = _scan_runtime_errors_with_watch(
        backend_key, log_path, log_text
    )
    log_byte_size = log_path.stat().st_size if log_path.is_file() else 0
    return {
        "ok": True,
        "db_alias": alias,
        "backend_project": project_name,
        "log_path": rel_log,
        "exists": log_path.is_file(),
        "content": content if content else ("（日志文件为空或尚未生成）" if log_path.is_file() else "（尚未启动过后端，无日志）"),
        "truncated": truncated,
        "runtime": runtime,
        "runtime_errors": runtime_errors,
        "new_runtime_errors": new_runtime_errors,
        "log_byte_size": log_byte_size,
    }


def _scan_runtime_errors_with_watch(
    backend_key: str,
    log_path: Path,
    tail_content: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from studio.runtime_log_monitor import scan_runtime_errors, scan_runtime_errors_chunk

    all_errors: list[dict[str, Any]] = []
    if tail_content.strip():
        all_errors = scan_runtime_errors(backend_key, tail_content)

    if not log_path.is_file():
        _LOG_WATCH_OFFSET[backend_key] = 0
        return all_errors, []

    size = log_path.stat().st_size
    prev = _LOG_WATCH_OFFSET.get(backend_key, 0)
    if size < prev:
        prev = 0

    new_errors: list[dict[str, Any]] = []
    if size > prev:
        try:
            with log_path.open("rb") as f:
                f.seek(prev)
                chunk = f.read(size - prev).decode("utf-8", errors="replace")
            if chunk.strip():
                new_errors = scan_runtime_errors_chunk(backend_key, chunk, prev)
        except OSError:
            new_errors = []

    _LOG_WATCH_OFFSET[backend_key] = size
    return all_errors, new_errors


def get_backend_runtime(db_alias: str, project_name: str) -> dict[str, Any] | None:
    key = _registry_key(db_alias, project_name)
    proc = _REGISTRY.get(key)
    if not proc or proc.process.poll() is not None:
        return None
    if not _is_port_open("127.0.0.1", proc.port):
        return None
    host = f"http://127.0.0.1:{proc.port}".rstrip("/")
    suffix = (proc.api_prefix or "").rstrip("/")
    base = host if not suffix else f"{host}{suffix}"
    return {
        "backend_project": project_name,
        "port": proc.port,
        "api_base_url": base,
        "running": True,
    }


def stop_backends_for_alias(db_alias: str) -> list[str]:
    """停止指定 saas 下由 Studio 托管的后端预览进程。"""
    alias = validate_db_alias(db_alias)
    prefix = f"{alias}::"
    stopped: list[str] = []
    for key in list(_REGISTRY.keys()):
        if not key.startswith(prefix):
            continue
        proc = _REGISTRY.get(key)
        if proc:
            stopped.append(proc.project_name)
        _stop_registered(key)
        project_name = key.split("::", 1)[-1]
        reset_runtime_log_watch(alias, project_name)
    return stopped


def shutdown_all_backends() -> None:
    for key in list(_REGISTRY.keys()):
        _stop_registered(key)


atexit.register(shutdown_all_backends)
