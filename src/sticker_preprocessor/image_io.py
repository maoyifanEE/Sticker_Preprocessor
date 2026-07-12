from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import (
    AnimatedImageError,
    ImageTooLargeError,
    InvalidImageError,
    LoadedImage,
    UnsupportedFormatError,
)

LOGGER = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_DIMENSION = 12_000
MIN_DIMENSION = 2


def _validate_dimensions(width: int, height: int) -> None:
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        raise ImageTooLargeError("图片尺寸过小。", code="IMAGE_TOO_SMALL")
    if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
        raise ImageTooLargeError()


def load_image(path: str | Path) -> LoadedImage:
    image_path = Path(path)
    LOGGER.info("file_selected name=%s", image_path.name)
    if not image_path.is_file():
        raise InvalidImageError("图片文件不存在。")
    if image_path.stat().st_size > MAX_FILE_SIZE:
        raise ImageTooLargeError("图片文件过大。")
    try:
        with Image.open(image_path) as probe:
            detected = (probe.format or "").upper()
            original_mode = probe.mode
            if detected not in SUPPORTED_FORMATS:
                raise UnsupportedFormatError()
            if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) > 1:
                raise AnimatedImageError()
            _validate_dimensions(*probe.size)
            probe.verify()
        with Image.open(image_path) as reopened:
            if getattr(reopened, "is_animated", False) or getattr(reopened, "n_frames", 1) > 1:
                raise AnimatedImageError()
            image = ImageOps.exif_transpose(reopened)
            _validate_dimensions(*image.size)
            rgba = image.convert("RGBA")
    except (UnsupportedFormatError, AnimatedImageError, ImageTooLargeError):
        LOGGER.info("validation_failed name=%s", image_path.name)
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        LOGGER.info("validation_failed name=%s reason=decode_error", image_path.name)
        raise InvalidImageError() from exc
    LOGGER.info(
        "validation_succeeded name=%s format=%s width=%s height=%s",
        image_path.name,
        detected,
        rgba.width,
        rgba.height,
    )
    return LoadedImage(image_path, rgba, detected, original_mode)
