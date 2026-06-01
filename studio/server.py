"""Skill Studio Web 服务。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Literal

from pydantic import BaseModel, Field, model_validator

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from studio.frontend_preview import guess_media_type  # noqa: E402
from studio.services import (  # noqa: E402
    complete_setup,
    create_skill_author_session,
    create_skill_file,
    create_conversation,
    delete_conversation,
    delete_custom_skill,
    delete_skill_path,
    delete_project,
    get_conversation,
    get_project_setup_form,
    get_studio_skill_detail,
    get_skill_file,
    get_status,
    get_system_preview_summary,
    get_system_preview_backend_log,
    restart_system_preview_backend,
    start_system_preview_backend,
    create_workspace_artifact,
    delete_workspace_artifact,
    get_workspace_artifact,
    list_conversations,
    list_frontend_projects,
    list_projects,
    list_studio_skills,
    list_skill_author_session_files,
    list_tool_labels,
    list_workspace_artifacts,
    persist_conversation_messages,
    remove_project_source_file,
    resolve_frontend_preview_path,
    save_workspace_artifact,
    save_skill_file,
    select_project,
    stream_chat,
    upload_custom_skill_folder,
    upload_custom_skill_zip,
    upload_project_source_files,
    upload_skill_author_files,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Skill Studio", version="1.3")


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "version": "1.3",
        "features": ["conversations", "multi_skill", "chat_memory", "artifacts"],
    }


class SetupRequest(BaseModel):
    db_alias: str = Field(..., description="工作区别名")
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = Field("", description="源库账号（配置了源库时填写）")
    password: str = ""
    source_databases: list[str] = Field(default_factory=list, description="已有源库，可多个，可留空")
    target_database: str = Field("", description="目标库，可留空；留空则后端数据存 saas 本地 SQLite")
    target_user: str | None = Field(None, description="目标库账号，默认同 user")
    target_password: str | None = Field(None, description="目标库密码，默认同 password")
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_provider: str = "deepseek"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    test_connection: bool = True


class SelectProjectRequest(BaseModel):
    db_alias: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ArtifactSaveRequest(BaseModel):
    path: str = Field(..., min_length=1, description="相对路径，如 dataset/foo.md")
    content: str = Field(default="")


class SkillFileSaveRequest(BaseModel):
    path: str = Field(..., min_length=1, description="skill 目录内相对路径")
    content: str = Field(default="")


class ArtifactCreateRequest(BaseModel):
    path: str = Field(..., min_length=1, description="相对路径，如 dataset/foo.md")
    content: str = Field(default="", description="初始内容，可空")


class SystemPreviewStartRequest(BaseModel):
    frontend_project: str | None = Field(
        None, description="前端工程名，用于解析 linked_frontend 对应的后端"
    )
    backend_project: str | None = Field(None, description="直接指定后端工程名")


class ChatRequest(BaseModel):
    """对话请求。优先使用 skills；skill 为兼容旧版前端保留。"""

    skills: list[str] | None = Field(
        None,
        description="启用的 skill 目录名列表",
    )
    skill: str | None = Field(
        None,
        description="兼容旧版：单个 skill 名",
    )
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="当前对话中此前的 user/assistant 消息（不含本条 message）",
    )
    conversation_id: str | None = Field(
        None,
        description="工作区 conversations/ 下的对话 id；省略则自动新建",
    )
    mode: Literal["normal", "skill_author"] = Field(
        default="normal",
        description="skill_author 模式仅启用 skill_author，用于创建自定义 Skill",
    )
    skill_author_session: str | None = Field(
        None,
        description="Skill 创建会话 id（上传参考文件用）",
    )

    @model_validator(mode="after")
    def _normalize_skills(self) -> "ChatRequest":
        if self.mode == "skill_author":
            self.skills = ["skill_author"]
            return self
        normalized: list[str] = []
        if self.skills:
            normalized = [str(s).strip() for s in self.skills if str(s).strip()]
        elif self.skill and str(self.skill).strip():
            normalized = [str(self.skill).strip()]
        if not normalized:
            raise ValueError("请至少选择一个 skill（请求体字段 skills）")
        self.skills = normalized
        return self


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def api_status():
    return get_status()


@app.get("/api/projects")
async def api_projects():
    return {"ok": True, "projects": list_projects()}


@app.get("/api/skills")
async def api_skills():
    return {"ok": True, "skills": list_studio_skills(include_hidden=True)}


@app.get("/api/skills/{skill_id}")
async def api_skill_detail(skill_id: str):
    try:
        return {"ok": True, "skill": get_studio_skill_detail(skill_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/skills/{skill_id}/file")
async def api_get_skill_file(skill_id: str, path: str):
    try:
        return {"ok": True, **get_skill_file(skill_id, path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.put("/api/skills/{skill_id}/file")
async def api_save_skill_file(skill_id: str, body: SkillFileSaveRequest):
    try:
        return {"ok": True, **save_skill_file(skill_id, body.path, body.content)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/skills/{skill_id}/file")
async def api_create_skill_file(skill_id: str, body: SkillFileSaveRequest):
    try:
        return {"ok": True, **create_skill_file(skill_id, body.path, body.content)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/api/skills/{skill_id}/file")
async def api_delete_skill_file(skill_id: str, path: str):
    try:
        return {"ok": True, **delete_skill_path(skill_id, path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/custom-skills/upload")
async def api_upload_custom_skill(
    file: UploadFile = File(...),
    skill_id: str | None = None,
):
    try:
        data = await file.read()
        return {"ok": True, **upload_custom_skill_zip(data, skill_id=skill_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/custom-skills/upload-folder")
async def api_upload_custom_skill_folder(request: Request):
    try:
        form = await request.form()
        path_list = [str(p).strip().replace("\\", "/").lstrip("/") for p in form.getlist("paths")]
        file_items = form.getlist("files")
        payload: list[tuple[str, bytes]] = []
        for i, item in enumerate(file_items):
            if not hasattr(item, "read"):
                continue
            rel = path_list[i] if i < len(path_list) else ""
            if not rel:
                rel = (getattr(item, "filename", None) or "").replace("\\", "/").lstrip("/")
            if not rel:
                continue
            payload.append((rel, await item.read()))
        if not payload:
            raise ValueError("未收到任何文件，请选中整个 skill 文件夹后重试")
        skill_id = form.get("skill_id")
        sid = str(skill_id).strip() if skill_id else None
        return {
            "ok": True,
            **upload_custom_skill_folder(payload, skill_id=sid or None),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/api/custom-skills/{skill_id}")
async def api_delete_custom_skill(skill_id: str):
    try:
        return {"ok": True, **delete_custom_skill(skill_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/skill-author/session")
async def api_skill_author_session():
    return {"ok": True, **create_skill_author_session()}


@app.get("/api/skill-author/uploads")
async def api_list_skill_author_uploads(session_id: str):
    try:
        return {"ok": True, **list_skill_author_session_files(session_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/skill-author/uploads")
async def api_upload_skill_author_files(session_id: str, files: list[UploadFile] = File(...)):
    try:
        payload: list[tuple[str, bytes]] = []
        for uf in files:
            payload.append((uf.filename or "file", await uf.read()))
        return {"ok": True, **upload_skill_author_files(session_id, payload)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/tool-labels")
async def api_tool_labels():
    return {"ok": True, "labels": list_tool_labels()}


@app.get("/api/projects/{db_alias}")
async def api_project_detail(db_alias: str):
    try:
        return {"ok": True, "project": get_project_setup_form(db_alias)}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/projects/select")
async def api_select_project(body: SelectProjectRequest):
    try:
        return {"ok": True, "status": select_project(body.db_alias)}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/projects/{db_alias}")
async def api_delete_project(db_alias: str):
    try:
        return delete_project(db_alias)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}") from e


@app.post("/api/projects/{db_alias}/source-files")
async def api_upload_source_files(db_alias: str, files: list[UploadFile] = File(...)):
    try:
        payload: list[tuple[str, bytes]] = []
        for item in files:
            name = item.filename or "upload"
            content = await item.read()
            payload.append((name, content))
        return {"ok": True, **upload_project_source_files(db_alias, payload)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {e}") from e


@app.delete("/api/projects/{db_alias}/source-files")
async def api_delete_source_file(db_alias: str, path: str):
    try:
        return {"ok": True, **remove_project_source_file(db_alias, path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}") from e


@app.post("/api/setup")
async def api_setup(body: SetupRequest):
    try:
        return complete_setup(
            db_alias=body.db_alias,
            host=body.host,
            port=body.port,
            user=body.user,
            password=body.password,
            source_databases=body.source_databases,
            target_database=body.target_database,
            target_user=body.target_user,
            target_password=body.target_password,
            deepseek_api_key=body.deepseek_api_key,
            deepseek_base_url=body.deepseek_base_url,
            deepseek_model=body.deepseek_model,
            llm_provider=body.llm_provider,
            gemini_api_key=body.gemini_api_key,
            gemini_model=body.gemini_model,
            test_connection=body.test_connection,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/conversations")
async def api_list_conversations():
    try:
        return {"ok": True, "conversations": list_conversations()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/conversations")
async def api_create_conversation():
    try:
        conv = create_conversation()
        return {"ok": True, "conversation": conv}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/frontend/projects")
async def api_frontend_projects():
    try:
        return {"ok": True, "projects": list_frontend_projects()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/system-preview")
async def api_system_preview():
    status = get_status()
    if not status.get("ready"):
        raise HTTPException(status_code=400, detail="请先完成初始化配置")
    try:
        return {"ok": True, **get_system_preview_summary()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _frontend_preview_response(
    project_name: str,
    file_path: str | None,
    studio_api_base: str | None = None,
):
    try:
        path = resolve_frontend_preview_path(project_name, file_path)
        if studio_api_base and path.suffix.lower() in (".html", ".htm"):
            from studio.backend_runner import inject_studio_api_base

            content = path.read_text(encoding="utf-8")
            body = inject_studio_api_base(content, studio_api_base)
            return Response(content=body, media_type=guess_media_type(path))
        return FileResponse(path, media_type=guess_media_type(path))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/frontend-preview/{project_name}")
async def api_frontend_preview_entry(
    project_name: str,
    studio_api_base: str | None = None,
):
    return _frontend_preview_response(project_name, None, studio_api_base)


@app.get("/api/frontend-preview/{project_name}/{file_path:path}")
async def api_frontend_preview_file(
    project_name: str,
    file_path: str,
    studio_api_base: str | None = None,
):
    return _frontend_preview_response(project_name, file_path, studio_api_base)


@app.post("/api/system-preview/start")
async def api_system_preview_start(body: SystemPreviewStartRequest):
    status = get_status()
    if not status.get("ready"):
        raise HTTPException(status_code=400, detail="请先完成初始化配置")
    try:
        return await asyncio.to_thread(
            start_system_preview_backend,
            frontend_project=body.frontend_project,
            backend_project=body.backend_project,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/system-preview/restart")
async def api_system_preview_restart(body: SystemPreviewStartRequest):
    status = get_status()
    if not status.get("ready"):
        raise HTTPException(status_code=400, detail="请先完成初始化配置")
    try:
        return await asyncio.to_thread(
            restart_system_preview_backend,
            frontend_project=body.frontend_project,
            backend_project=body.backend_project,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/system-preview/backend-log")
async def api_system_preview_backend_log(
    frontend_project: str | None = None,
    backend_project: str | None = None,
    tail_lines: int = 500,
    reset_watch: bool = False,
):
    status = get_status()
    if not status.get("ready"):
        raise HTTPException(status_code=400, detail="请先完成初始化配置")
    try:
        return get_system_preview_backend_log(
            frontend_project=frontend_project,
            backend_project=backend_project,
            tail_lines=tail_lines,
            reset_watch=reset_watch,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/artifacts")
async def api_list_artifacts():
    try:
        return {"ok": True, **list_workspace_artifacts()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/artifacts/file")
async def api_get_artifact(path: str):
    try:
        return {"ok": True, "file": get_workspace_artifact(path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.put("/api/artifacts/file")
async def api_save_artifact(body: ArtifactSaveRequest):
    try:
        return {"ok": True, "file": save_workspace_artifact(body.path, body.content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/artifacts/file")
async def api_create_artifact(body: ArtifactCreateRequest):
    try:
        return {"ok": True, "file": create_workspace_artifact(body.path, body.content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/artifacts/file")
async def api_delete_artifact(path: str):
    try:
        return {"ok": True, **delete_workspace_artifact(path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}") from e


@app.get("/api/conversations/{conversation_id}")
async def api_get_conversation(conversation_id: str):
    try:
        return {"ok": True, "conversation": get_conversation(conversation_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/api/conversations/{conversation_id}")
async def api_delete_conversation(conversation_id: str):
    try:
        result = delete_conversation(conversation_id)
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/chat")
async def api_chat(body: ChatRequest):
    status = get_status()
    if not status.get("ready"):
        raise HTTPException(status_code=400, detail="请先完成初始化配置")

    def event_stream():
        assistant_parts: list[str] = []
        try:
            hist = [{"role": m.role, "content": m.content} for m in body.history]
            for chunk in stream_chat(
                body.skills,
                body.message,
                history=hist,
                mode=body.mode,
                skill_author_session=body.skill_author_session,
            ):
                assistant_parts.append(chunk)
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            reply = "".join(assistant_parts)
            messages = hist + [
                {"role": "user", "content": body.message.strip()},
                {"role": "assistant", "content": reply.strip()},
            ]
            conv = persist_conversation_messages(
                body.conversation_id,
                messages,
            )
            meta = {
                "conversation_id": conv["id"],
                "title": conv.get("title", ""),
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
