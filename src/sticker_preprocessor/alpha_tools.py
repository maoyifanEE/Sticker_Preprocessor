from __future__ import annotations

import logging
from collections import deque

import numpy as np
from PIL import Image

from .diagnostics import (
    ALPHA_SOURCE_HAZE_CUTOFF,
    GENERATED_RESULT_HAZE_CUTOFF,
    HazeCleanupResult,
    analyze_alpha,
)
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
        LOGGER.info("alpha.trim_failed reason=empty_foreground threshold=%s", alpha_threshold)
        raise EmptyForegroundError()
    left = int(xs.min())
    top = int(ys.min())
    right = int(xs.max()) + 1
    bottom = int(ys.max()) + 1
    foreground = rgba.crop((left, top, right, bottom))
    if padding > 0:
        canvas = Image.new("RGBA", (foreground.width + 2 * padding, foreground.height + 2 * padding), (0, 0, 0, 0))
        canvas.alpha_composite(foreground, (padding, padding))
        cleaned = clear_rgb_where_alpha_zero(canvas)
    else:
        cleaned = clear_rgb_where_alpha_zero(foreground)
    LOGGER.info(
        "alpha.trim_completed input=%sx%s output=%sx%s threshold=%s padding=%s",
        rgba.width,
        rgba.height,
        cleaned.width,
        cleaned.height,
        alpha_threshold,
        padding,
    )
    return cleaned


def _border_connected(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        if mask[0, x]:
            queue.append((x, 0))
        if mask[h - 1, x]:
            queue.append((x, h - 1))
    for y in range(h):
        if mask[y, 0]:
            queue.append((0, y))
        if mask[y, w - 1]:
            queue.append((w - 1, y))
    while queue:
        x, y = queue.popleft()
        if visited[y, x] or not mask[y, x]:
            continue
        visited[y, x] = True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and mask[ny, nx]:
                queue.append((nx, ny))
    return visited


def remove_border_connected_alpha_haze(
    image: Image.Image,
    *,
    threshold: int = GENERATED_RESULT_HAZE_CUTOFF,
    padding: int = 0,
    force: bool = True,
) -> HazeCleanupResult:
    rgba = image.convert("RGBA")
    before = analyze_alpha(rgba, padding=padding, haze_threshold=threshold)
    if not force and not before.low_alpha_haze_suspected:
        LOGGER.info("alpha.haze_cleanup_skipped threshold=%s reason=no_signature", threshold)
        return HazeCleanupResult(rgba.copy(), 0, threshold, before, before, ("NO_HAZE_SIGNATURE",))
    arr = np.array(rgba, copy=True)
    alpha = arr[:, :, 3]
    candidate = (alpha > 0) & (alpha <= threshold)
    connected = _border_connected(candidate)
    removed = int(np.count_nonzero(connected))
    if removed:
        arr[connected, 3] = 0
        arr[arr[:, :, 3] == 0, :3] = 0
    cleaned = Image.fromarray(arr, "RGBA")
    after = analyze_alpha(cleaned, padding=padding, haze_threshold=threshold)
    LOGGER.info("alpha.haze_cleanup_succeeded threshold=%s removed_pixels=%s", threshold, removed)
    return HazeCleanupResult(cleaned, removed, threshold, before, after, ())


def haze_threshold_for_route(route: str) -> int:
    if route == "alpha_cleanup":
        return ALPHA_SOURCE_HAZE_CUTOFF
    return GENERATED_RESULT_HAZE_CUTOFF
