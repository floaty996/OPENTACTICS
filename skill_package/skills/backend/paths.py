"""backend skill 产出目录 → workspace/{db_alias}/backend/"""

from skill_package.workspace.paths import (
    TEMPLATES_ROOT,
    WORKSPACE_ROOT,
    backend_dir,
    config_path,
    ensure_workspace,
    validate_db_alias,
)

API_MANIFEST_NAME = "api_manifest.json"
API_MANIFEST_TEMPLATE = TEMPLATES_ROOT / "api_manifest.json"
API_KNOWLEDGE_NAME = "api_knowledge.md"
API_KNOWLEDGE_TEMPLATE = TEMPLATES_ROOT / "api_knowledge.md"
