from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from .models import EmptyForegroundError

LOGGER = logging.getLogger(__name__)

DEFAULT_ALPHA_CROP_THRESHOLD = 8
DEFAULT_PADDING_PIXELS = 8


def clear_rgb_where_alpha_zero(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    arr = np.array(rgba, copy=True)
    mask = arr[:, :, 3] == 0
    arr[mask, :3] = 0
    return Image.fromarray(arr, "RGBA")


def trim_transparent_bounds(
    image: Image.Image,
    *,
    alpha_threshold: int = DEFAULT_ALPHA_CROP_THRESHOLD,
    padding: int = DEFAULT_PADDING_PIXELS,
) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    ys, xs = np.where(alpha > alpha_threshold)
    if not xs.size:
        LOGGER.info("trim_failed reason=empty_foreground threshold=%s", alpha_threshold)
        raise EmptyForegroundError()
    left = max(int(xs.min()) - padding, 0)
    top = max(int(ys.min()) - padding, 0)
    right = min(int(xs.max()) + 1 + padding, rgba.width)
    bottom = min(int(ys.max()) + 1 + padding, rgba.height)
    cropped = rgba.crop((left, top, right, bottom))
    cleaned = clear_rgb_where_alpha_zero(cropped)
    LOGGER.info(
        "trim_completed input=%sx%s output=%sx%s threshold=%s padding=%s",
        rgba.width,
        rgba.height,
        cleaned.width,
        cleaned.height,
        alpha_threshold,
        padding,
    )
    return cleaned
