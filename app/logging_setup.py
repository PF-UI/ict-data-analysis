"""应用内日志：保证 ``app.*`` 的 INFO 能出现在 uvicorn 终端（不依赖根 logger 配置）。"""
from __future__ import annotations

import logging
import sys

_configured = False


def ensure_app_package_logging() -> None:
    """为 ``app`` logger 挂载 StreamHandler；子模块如 ``app.agent_runtime.tools.neo4j_tool`` 会向上冒泡。"""
    global _configured
    if _configured:
        return
    app_log = logging.getLogger("app")
    if not app_log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(levelname)s [%(name)s] %(message)s")
        )
        app_log.addHandler(handler)
    app_log.setLevel(logging.INFO)
    # 避免与 uvicorn 根 handler 重复打印同一行（若根 logger 也为 INFO）
    app_log.propagate = False
    _configured = True
