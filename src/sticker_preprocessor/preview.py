from __future__ import annotations

import numpy as np
from PIL import Image

from .models import PreviewBackground

LIGHT_BACKGROUND = (244, 241, 234, 255)
DARK_BACKGROUND = (37, 42, 52, 255)
WEB_GRADIENT_START = np.array([232, 241, 250], dtype=np.float32)
WEB_GRADIENT_END = np.array([250, 240, 219], dtype=np.float32)


def make_preview(image: Image.Image, background: PreviewBackground, max_size: tuple[int, int]) -> Image.Image:
    rgba = image.convert("RGBA")
    preview = rgba.copy()
    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    bg = _background(preview.size, background)
    bg.alpha_composite(preview)
    return bg.convert("RGB")


def _background(size: tuple[int, int], background: PreviewBackground) -> Image.Image:
    if background == PreviewBackground.DARK:
        return Image.new("RGBA", size, DARK_BACKGROUND)
    if background == PreviewBackground.WEB:
        width, height = size
        if width <= 0 or height <= 0:
            return Image.new("RGBA", size, LIGHT_BACKGROUND)
        xs = np.linspace(0.0, 1.0, width, dtype=np.float32)
        ys = np.linspace(0.0, 1.0, height, dtype=np.float32)
        mix = (xs[None, :] + ys[:, None]) / 2.0
        rgb = WEB_GRADIENT_START * (1.0 - mix[:, :, None]) + WEB_GRADIENT_END * mix[:, :, None]
        alpha = np.full((height, width, 1), 255, dtype=np.uint8)
        return Image.fromarray(np.concatenate([rgb.astype(np.uint8), alpha], axis=2), "RGBA")
    return Image.new("RGBA", size, LIGHT_BACKGROUND)
