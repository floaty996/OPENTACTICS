"""database skill 产出目录 → workspace/{db_alias}/dataset/"""

from skill_package.workspace.paths import (
    TEMPLATES_ROOT,
    WORKSPACE_ROOT,
    dataset_dir,
    ensure_workspace,
    validate_db_alias,
)

# 模板（供 SKILL 引用）
DATASET_TEMPLATE = TEMPLATES_ROOT / "dataset_knowledge.md"
