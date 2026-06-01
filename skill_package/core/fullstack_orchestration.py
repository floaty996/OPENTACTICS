"""Studio multi-skill full-stack orchestration notes (injected into system prompt, not written to workspace)."""

from __future__ import annotations


def build_fullstack_orchestration_note(skill_ids: list[str]) -> str:
    """When backend and UI_build are both enabled, return full-stack delivery constraints."""
    ids = set(skill_ids)
    if "backend" not in ids or "UI_build" not in ids:
        return ""

    lines = [
        "\n[Full-stack generation — priority: system starts and integrates]",
        "For new systems call get_fullstack_generation_spec first; violating save_*_file returns blocked: true.",
        "",
        "Standard order (do not skip steps):",
    ]
    if "database" in ids:
        lines.append("1. database: dataset + target DB tables")
    step = 2 if "database" in ids else 1
    lines.extend(
        [
            f"{step}. scaffold_fullstack_project (or hand-write manifest/main/preview per templates)",
            f"{step + 1}. backend: save_backend_file for routers; no unprefixed add_api_route shims",
            f"{step + 2}. get_fullstack_api_contract → apiGet paths from route_fetch_map",
            f"{step + 3}. UI_build: save_ui_file for preview.html (apiGet/apiPost only)",
            f"{step + 4}. verify_fullstack_deliverables → system_complete true before telling user the system is done",
            "",
            "Write gates:",
            "- save_backend_file / patch: relative imports, dual routes, invalid manifest → rejected",
            "- save_ui_file: const API, hardcoded ports, contract failures → rejected or blocked",
            "- Do not claim the system runs until verify passes",
        ]
    )
    return "\n".join(lines) + "\n"
