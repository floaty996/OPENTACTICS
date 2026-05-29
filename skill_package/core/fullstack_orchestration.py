"""Studio 多 skill 全栈编排说明（注入 system prompt，不修改 workspace）。"""

from __future__ import annotations


def build_fullstack_orchestration_note(skill_ids: list[str]) -> str:
    """当 backend 与 UI_build 同时启用时，返回全栈交付约束文案。"""
    ids = set(skill_ids)
    if "backend" not in ids or "UI_build" not in ids:
        return ""

    lines = [
        "\n【全栈生成硬性规范 — 首要目标：系统能启动、能对接】",
        "新建系统时先调用 get_fullstack_generation_spec；违反规范的 save_*_file 会被拒绝（blocked: true）。",
        "",
        "标准顺序（不得跳步）：",
    ]
    if "database" in ids:
        lines.append("1. database：dataset + 目标库表")
    step = 2 if "database" in ids else 1
    lines.extend(
        [
            f"{step}. scaffold_fullstack_project（或严格按模板手写 manifest/main/preview）",
            f"{step + 1}. backend：save_backend_file 补充 routers；禁止 add_api_route 无前缀兼容",
            f"{step + 2}. get_fullstack_api_contract → 按 route_fetch_map 写 apiGet 路径",
            f"{step + 3}. UI_build：save_ui_file 写 preview.html（只用 apiGet/apiPost）",
            f"{step + 4}. verify_fullstack_deliverables → system_complete 为 true 才能对用户说「系统完成」",
            "",
            "写盘门禁：",
            "- save_backend_file / patch：相对导入、双轨路由、非法 manifest → 拒绝写入",
            "- save_ui_file：const API、硬编码端口、契约检查失败 → 拒绝或 blocked",
            "- 向用户声称可运行前：必须 verify 通过",
        ]
    )
    return "\n".join(lines) + "\n"
