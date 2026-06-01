"""
Skill Studio compatible FastAPI entry template (copy to backend/{project}/main.py and adapt).

Studio backend_runner: uvicorn main:app --host 127.0.0.1 --port {default_port}
This file must import cleanly and expose `app`.
"""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="API")

# Single route prefix (recommended): matches api_manifest.json api_prefix="/api"
api_router = APIRouter(prefix="/api")

# If you need both unprefixed and /api paths, define direct_router and register it (do not use bare decorators only)
# direct_router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api_router.get("/health")
def health():
    return {"status": "ok"}


app.include_router(api_router)
# If using direct_router: app.include_router(direct_router)


def get_db_config_hint() -> str:
    """database.py should prefer env vars (injected in Studio preview)."""
    return "Read STUDIO_WORKSPACE_CONFIG / STUDIO_LOCAL_SQLITE when storage_mode=local"
