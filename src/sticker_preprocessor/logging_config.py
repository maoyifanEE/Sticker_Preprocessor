from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from .runtime_paths import logs_dir

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s event=%(message)s"


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_sticker_logging_configured", False):
        return
    root.setLevel(logging.INFO)
    try:
        log_dir = logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(
            log_dir / "sticker_preprocessor.log",
            when="midnight",
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    except Exception as exc:  # pragma: no cover - logging must not crash launch
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(stream)
        root.warning("logging_file_unavailable reason=%s", exc)
    root._sticker_logging_configured = True  # type: ignore[attr-defined]
