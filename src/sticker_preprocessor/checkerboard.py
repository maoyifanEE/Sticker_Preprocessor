from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .alpha_tools import trim_transparent_bounds
from .models import CheckerboardAnalysis, CheckerboardNotDetectedError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckerboardSettings:
    min_luminance: int = 165
    max_channel_spread: int = 40
    min_color_distance: float = 5.0
    max_color_distance: float = 90.0
    min_border_coverage: float = 0.60
    min_confidence: float = 0.85
    min_tile_size: int = 4
    max_tile_size: int = 160
    close_tolerance: float = 18.0
    far_tolerance: float = 42.0


SETTINGS = CheckerboardSettings()


def _empty(warnings: tuple[str, ...] = ()) -> CheckerboardAnalysis:
    return CheckerboardAnalysis(False, 0.0, None, None, None, None, 0.0, 0.0, warnings)


def _is_light_neutral(color: np.ndarray) -> bool:
    return float(color.mean()) >= SETTINGS.min_luminance and int(color.max() - color.min()) <= SETTINGS.max_channel_spread


def _border_pixels(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    strip = max(2, min(h, w) // 20)
    parts = [
        rgb[:strip, :, :].reshape(-1, 3),
        rgb[h - strip :, :, :].reshape(-1, 3),
        rgb[:, :strip, :].reshape(-1, 3),
        rgb[:, w - strip :, :].reshape(-1, 3),
    ]
    return np.vstack(parts)


def _dominant_two_colors(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
    quantized = (pixels // 8) * 8
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    if len(colors) < 2:
        return None
    order = np.argsort(counts)[::-1]
    first = colors[order[0]].astype(float) + 4
    for idx in order[1:20]:
        second = colors[idx].astype(float) + 4
        distance = float(np.linalg.norm(first - second))
        if SETTINGS.min_color_distance <= distance <= SETTINGS.max_color_distance:
            coverage = float((counts[order[0]] + counts[idx]) / len(pixels))
            return first, second, coverage
    return None


def _estimate_tile_size(labels: np.ndarray) -> int | None:
    mid_y = labels.shape[0] // 2
    mid_x = labels.shape[1] // 2
    runs: list[int] = []
    for line in (labels[mid_y, :], labels[:, mid_x], labels[0, :], labels[-1, :]):
        current = line[0]
        length = 1
        for value in line[1:]:
            if value == current:
                length += 1
            else:
                if current in (0, 1):
                    runs.append(length)
                current = value
                length = 1
        if current in (0, 1):
            runs.append(length)
    runs = [r for r in runs if SETTINGS.min_tile_size <= r <= SETTINGS.max_tile_size]
    if len(runs) < 4:
        return None
    return int(round(float(np.median(runs))))


def _pattern_accuracy(labels: np.ndarray, tile: int, phase: tuple[int, int]) -> tuple[float, bool]:
    h, w = labels.shape
    step = max(1, min(tile // 2, 8))
    ys = np.arange(0, h, step)
    xs = np.arange(0, w, step)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    expected = (((xx + phase[0]) // tile) + ((yy + phase[1]) // tile)) % 2
    sampled = labels[yy, xx]
    valid = sampled >= 0
    if not np.any(valid):
        return 0.0, False
    direct = float(np.mean(sampled[valid] == expected[valid]))
    inverse = 1.0 - direct
    return (inverse, True) if inverse > direct else (direct, False)


def analyze_checkerboard(image: Image.Image) -> CheckerboardAnalysis:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    if int(np.count_nonzero(alpha < 250)) > max(64, alpha.size // 10000):
        return _empty(("source_has_real_alpha",))
    rgb = np.asarray(rgba.convert("RGB"), dtype=np.uint8)
    dominant = _dominant_two_colors(_border_pixels(rgb))
    if dominant is None:
        LOGGER.info("checkerboard_analysis_completed detected=false reason=no_dominant_colors")
        return _empty(("no_dominant_colors",))
    c1, c2, raw_coverage = dominant
    if not (_is_light_neutral(c1) and _is_light_neutral(c2)):
        return _empty(("colors_not_light_neutral",))
    dist1 = np.linalg.norm(rgb.astype(float) - c1, axis=2)
    dist2 = np.linalg.norm(rgb.astype(float) - c2, axis=2)
    nearest = np.minimum(dist1, dist2)
    labels = np.where(dist1 <= dist2, 0, 1).astype(np.int8)
    labels[nearest > SETTINGS.far_tolerance] = -1
    border = _border_pixels(np.repeat(labels[:, :, None], 3, axis=2))[:, 0]
    border_coverage = max(raw_coverage, float(np.mean(border >= 0)))
    if border_coverage < SETTINGS.min_border_coverage:
        return _empty(("low_border_coverage",))
    tile = _estimate_tile_size(labels)
    if tile is None or not SETTINGS.min_tile_size <= tile <= SETTINGS.max_tile_size:
        return _empty(("tile_size_unreliable",))
    phases = [(0, 0), (tile // 2, 0), (0, tile // 2), (tile // 2, tile // 2)]
    phase_scores = [(phase, *_pattern_accuracy(labels, tile, phase)) for phase in phases]
    phase, accuracy, inverted = max(phase_scores, key=lambda item: item[1])
    if inverted:
        c1, c2 = c2, c1
    confidence = min(1.0, accuracy * 0.75 + min(border_coverage, 1.0) * 0.25)
    detected = confidence >= SETTINGS.min_confidence
    result = CheckerboardAnalysis(
        detected=detected,
        confidence=confidence,
        first_color=tuple(int(round(x)) for x in c1),
        second_color=tuple(int(round(x)) for x in c2),
        estimated_tile_size=tile,
        phase=phase,
        border_coverage=border_coverage,
        pattern_accuracy=accuracy,
        warnings=() if detected else ("low_confidence",),
    )
    LOGGER.info(
        "checkerboard_analysis_completed detected=%s confidence=%.3f tile=%s",
        result.detected,
        result.confidence,
        result.estimated_tile_size,
    )
    return result


def _border_connected(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        if mask[0, x]:
            q.append((x, 0))
        if mask[h - 1, x]:
            q.append((x, h - 1))
    for y in range(h):
        if mask[y, 0]:
            q.append((0, y))
        if mask[y, w - 1]:
            q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        if visited[y, x] or not mask[y, x]:
            continue
        visited[y, x] = True
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and mask[ny, nx]:
                q.append((nx, ny))
    return visited


def remove_checkerboard(
    image: Image.Image,
    analysis: CheckerboardAnalysis | None = None,
    *,
    padding: int = 8,
    alpha_threshold: int = 8,
) -> tuple[Image.Image, CheckerboardAnalysis]:
    result_analysis = analysis or analyze_checkerboard(image)
    if (
        not result_analysis.detected
        or result_analysis.first_color is None
        or result_analysis.second_color is None
        or result_analysis.estimated_tile_size is None
        or result_analysis.phase is None
    ):
        raise CheckerboardNotDetectedError()
    rgba = image.convert("RGBA")
    arr = np.array(rgba, copy=True)
    rgb = arr[:, :, :3].astype(float)
    h, w, _ = arr.shape
    yy, xx = np.indices((h, w))
    tile = result_analysis.estimated_tile_size
    phase_x, phase_y = result_analysis.phase
    parity = (((xx + phase_x) // tile) + ((yy + phase_y) // tile)) % 2
    c1 = np.array(result_analysis.first_color, dtype=float)
    c2 = np.array(result_analysis.second_color, dtype=float)
    expected = np.where(parity[:, :, None] == 0, c1, c2)
    dist = np.linalg.norm(rgb - expected, axis=2)
    candidate = dist <= SETTINGS.far_tolerance
    connected = _border_connected(candidate)
    close = dist <= SETTINGS.close_tolerance
    partial = connected & ~close
    arr[connected & close, 3] = 0
    if np.any(partial):
        ratio = (dist[partial] - SETTINGS.close_tolerance) / (SETTINGS.far_tolerance - SETTINGS.close_tolerance)
        arr[partial, 3] = np.clip(ratio * 255, 0, 255).astype(np.uint8)
    arr[arr[:, :, 3] == 0, :3] = 0
    cleaned = Image.fromarray(arr, "RGBA")
    trimmed = trim_transparent_bounds(cleaned, alpha_threshold=alpha_threshold, padding=padding)
    LOGGER.info("checkerboard_removal_completed output=%sx%s", trimmed.width, trimmed.height)
    return trimmed, result_analysis
