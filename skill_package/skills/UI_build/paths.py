"""UI_build skill 产出目录 → workspace/{db_alias}/frontend/"""

from skill_package.workspace.paths import (
    TEMPLATES_ROOT,
    WORKSPACE_ROOT,
    config_path,
    ensure_workspace,
    frontend_dir,
    validate_db_alias,
)

UI_MANIFEST_NAME = "ui_manifest.json"
UI_MANIFEST_TEMPLATE = TEMPLATES_ROOT / "ui_manifest.json"
UI_KNOWLEDGE_NAME = "ui_knowledge.md"
UI_KNOWLEDGE_TEMPLATE = TEMPLATES_ROOT / "ui_knowledge.md"
