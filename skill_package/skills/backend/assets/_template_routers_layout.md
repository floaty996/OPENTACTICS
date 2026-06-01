# Multi-file backend layout (Studio compatible)

Skill Studio starts with `uvicorn main:app` in `backend/{project}/`. **No relative imports** in any `.py`.

## Directory layout

```
backend/{project}/
├── main.py
├── database.py
├── requirements.txt
├── api_manifest.json
└── routers/
    ├── __init__.py      # may be empty but should exist
    ├── employees.py
    └── stations.py
```

## main.py (correct)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import employees, stations  # absolute import; not from .routers

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(employees.router)
app.include_router(stations.router)
```

## routers/stations.py (correct)

```python
from fastapi import APIRouter
from database import get_connection  # absolute import; not from ..database

router = APIRouter(prefix="/api/stations", tags=["stations"])
```

## Wrong (Studio first start will fail)

```python
# main.py — wrong
from .routers import stations, employees

# routers/stations.py — wrong
from ..database import get_connection
```

Typical log: `ImportError: attempted relative import with no known parent package`
