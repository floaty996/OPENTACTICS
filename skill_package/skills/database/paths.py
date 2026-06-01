"""database skill output → workspace/{db_alias}/dataset/"""

from skill_package.workspace.paths import (
    TEMPLATES_ROOT,
    WORKSPACE_ROOT,
    dataset_dir,
    ensure_workspace,
    validate_db_alias,
)

# Template referenced from SKILL.md
DATASET_TEMPLATE = TEMPLATES_ROOT / "dataset_knowledge.md"
