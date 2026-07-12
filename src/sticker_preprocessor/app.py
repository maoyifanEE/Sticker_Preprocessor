from __future__ import annotations

import logging

from .logging_config import setup_logging
from .runtime_paths import ensure_runtime_dirs

LOGGER = logging.getLogger(__name__)


def run() -> None:
    setup_logging()
    ensure_runtime_dirs()
    LOGGER.info("application_started")
    from .ui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()
