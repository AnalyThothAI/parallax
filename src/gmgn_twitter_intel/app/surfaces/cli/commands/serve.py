from __future__ import annotations

import uvicorn

from gmgn_twitter_intel.app.runtime.app import create_app
from gmgn_twitter_intel.platform.config.settings import load_settings
from gmgn_twitter_intel.platform.logging.setup import setup_logging


def handle_serve(_args: object) -> int:
    settings = load_settings()
    setup_logging(settings.log_file)
    uvicorn.run(
        create_app(settings=settings),
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
        ws_ping_interval=settings.ws_heartbeat_interval,
        ws_ping_timeout=settings.ws_heartbeat_interval * 2,
    )
    return 0
