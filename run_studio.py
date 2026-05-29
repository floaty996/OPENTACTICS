#!/usr/bin/env python3
"""
启动 Skill Studio Web 界面。

  pip install -r requirements-studio.txt
  pip install -r skill_package/requirements-database.txt
  python run_studio.py

浏览器打开 http://127.0.0.1:8765
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if __name__ == "__main__":
    import uvicorn

    from studio.server import app

    # 使用模块路径 + reload，修改 studio/ 下代码后保存即可生效（无需手动重启）
    uvicorn.run(
        "studio.server:app",
        host="127.0.0.1",
        port=8765,
        reload=True,
        reload_dirs=[str(_ROOT / "studio"), str(_ROOT / "agents")],
    )
