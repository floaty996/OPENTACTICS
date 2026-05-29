# 多文件后端工程模板（Studio 兼容）

Skill Studio 以 `uvicorn main:app` 在 `backend/{project}/` 目录启动，**禁止**任何 `.py` 使用相对导入。

## 目录结构

```
backend/{project}/
├── main.py
├── database.py
├── requirements.txt
├── api_manifest.json
└── routers/
    ├── __init__.py      # 可为空文件，但建议创建
    ├── stations.py
    └── employees.py
```

## main.py（正确）

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import employees, stations  # 绝对导入，勿写 from .routers

app = FastAPI(title="API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(stations.router)
app.include_router(employees.router)

@app.get("/api/health")
def health():
    return {"ok": True}
```

## routers/stations.py（正确）

```python
from fastapi import APIRouter

from database import get_connection  # 绝对导入，勿写 from ..database

router = APIRouter(prefix="/api/stations", tags=["stations"])
```

## 错误示例（会导致 Studio 首次启动失败）

```python
# main.py — 错误
from .routers import stations

# routers/stations.py — 错误
from ..database import get_connection
```

日志典型报错：`ImportError: attempted relative import with no known parent package`
