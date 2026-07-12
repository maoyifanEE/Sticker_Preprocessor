from __future__ import annotations

import logging

import numpy as np
from PIL import Image

from .models import ImageAnalysis

LOGGER = logging.getLogger(__name__)

MEANINGFUL_ALPHA_THRESHOLD = 250
MEANINGFUL_ALPHA_MIN_PIXELS = 64
MEANINGFUL_ALPHA_MIN_FRACTION = 0.0001


def has_alpha_channel(mode: str) -> bool:
    return mode in {"RGBA", "LA", "PA"} or "A" in mode


def analyze_image(image: Image.Image, *, original_mode: str, detected_format: str) -> ImageAnalysis:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    total = int(alpha.size)
    nonopaque = int(np.count_nonzero(alpha < 255))
    meaningful_count = int(np.count_nonzero(alpha < MEANINGFUL_ALPHA_THRESHOLD))
    semitransparent = int(np.count_nonzero((alpha > 0) & (alpha < 255)))
    fully_transparent = int(np.count_nonzero(alpha == 0))
    required = max(MEANINGFUL_ALPHA_MIN_PIXELS, int(total * MEANINGFUL_ALPHA_MIN_FRACTION))
    ys, xs = np.where(alpha > 0)
    bbox = None
    if xs.size:
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    analysis = ImageAnalysis(
        original_mode=original_mode,
        detected_format=detected_format,
        width=rgba.width,
        height=rgba.height,
        total_pixels=total,
        has_source_alpha_channel=has_alpha_channel(original_mode),
        alpha_min=int(alpha.min()),
        alpha_max=int(alpha.max()),
        fully_transparent_count=fully_transparent,
        semitransparent_count=semitransparent,
        nonopaque_count=nonopaque,
        transparent_fraction=nonopaque / total,
        meaningful_transparency=meaningful_count >= required,
        alpha_bbox=bbox,
        warnings=(),
    )
    LOGGER.info(
        "alpha_analysis_completed width=%s height=%s alpha_min=%s alpha_max=%s meaningful=%s",
        analysis.width,
        analysis.height,
        analysis.alpha_min,
        analysis.alpha_max,
        analysis.meaningful_transparency,
    )
    return analysis
