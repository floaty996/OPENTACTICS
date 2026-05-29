"""当前工作区「系统」预览：汇总 frontend / backend / dataset 产物。"""

from __future__ import annotations

from typing import Any

from skill_package.skills.backend.scripts.backend_assets import _scan_projects as scan_backend_projects
from studio.frontend_preview import list_frontend_projects
from skill_package.workspace.paths import read_manifest, validate_db_alias


def get_system_preview(db_alias: str) -> dict[str, Any]:
    alias = validate_db_alias(db_alias)
    manifest = read_manifest(alias)
    frontends = list_frontend_projects(alias)
    backends = [r for r in scan_backend_projects(alias) if r.get("db_alias") == alias]

    default_frontend: str | None = None
    for p in manifest.get("projects") or []:
        if p.get("preview_entry"):
            default_frontend = str(p.get("name") or "")
            break
    if not default_frontend:
        for f in frontends:
            if f.get("has_preview"):
                default_frontend = f["project_name"]
                break
    if not default_frontend and frontends:
        default_frontend = frontends[0]["project_name"]

    fe_enriched: list[dict[str, Any]] = []
    for f in frontends:
        name = f["project_name"]
        linked_be = next(
            (b for b in backends if b.get("linked_frontend") == name),
            None,
        )
        if not linked_be:
            linked_be = next(
                (b for b in backends if b.get("project_name") == name),
                None,
            )
        fe_enriched.append(
            {
                **f,
                "linked_backend": linked_be["project_name"] if linked_be else None,
                "api_base_url": (
                    f"http://127.0.0.1:{linked_be.get('default_port', 8000)}{linked_be.get('api_prefix', '/api')}"
                    if linked_be
                    else None
                ),
            }
        )

    return {
        "db_alias": alias,
        "default_frontend": default_frontend,
        "frontends": fe_enriched,
        "backends": backends,
        "knowledge_files": list(manifest.get("knowledge_files") or []),
        "has_any_preview": any(f.get("has_preview") for f in fe_enriched),
    }
