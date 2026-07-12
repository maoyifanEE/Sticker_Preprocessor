from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .models import ExportError, InvalidOutputError
from .runtime_paths import output_dir

LOGGER = logging.getLogger(__name__)
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    safe_name = INVALID_CHARS.sub("_", name)
    stem = Path(safe_name).stem or "sticker"
    cleaned = stem.strip(" .")
    return cleaned or "sticker"


def _ensure_png_rgba_with_alpha(path: Path) -> None:
    try:
        with Image.open(path) as img:
            if img.format != "PNG" or img.mode != "RGBA":
                raise InvalidOutputError()
            alpha = np.asarray(img.getchannel("A"), dtype=np.uint8)
            if int(np.count_nonzero(alpha < 250)) == 0:
                raise InvalidOutputError("导出的 PNG 没有真实透明像素。")
    except InvalidOutputError:
        raise
    except Exception as exc:
        raise InvalidOutputError() from exc


def choose_output_path(source_name: str, directory: Path | None = None) -> Path:
    out_dir = directory or output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    base = sanitize_filename(source_name)
    candidate = out_dir / f"{base}_sticker.png"
    index = 2
    while candidate.exists():
        candidate = out_dir / f"{base}_sticker_{index}.png"
        index += 1
    return candidate


def export_png(image: Image.Image, source_name: str, directory: Path | None = None) -> Path:
    out_path = choose_output_path(source_name, directory)
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    LOGGER.info("export_started name=%s", out_path.name)
    try:
        rgba = image.convert("RGBA")
        rgba.save(tmp_path, format="PNG")
        _ensure_png_rgba_with_alpha(tmp_path)
        os.replace(tmp_path, out_path)
        _ensure_png_rgba_with_alpha(out_path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        LOGGER.exception("export_failed name=%s", out_path.name)
        if isinstance(exc, InvalidOutputError):
            raise
        raise ExportError(str(exc)) from exc
    LOGGER.info("export_succeeded name=%s", out_path.name)
    return out_path
