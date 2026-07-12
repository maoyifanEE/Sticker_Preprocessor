from __future__ import annotations

from PIL import Image, ImageDraw

from .models import PreviewBackground


def make_preview(image: Image.Image, background: PreviewBackground, max_size: tuple[int, int]) -> Image.Image:
    rgba = image.convert("RGBA")
    preview = rgba.copy()
    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    bg = _background(preview.size, background)
    bg.alpha_composite(preview)
    return bg.convert("RGB")


def _background(size: tuple[int, int], background: PreviewBackground) -> Image.Image:
    if background == PreviewBackground.DARK:
        return Image.new("RGBA", size, (40, 40, 40, 255))
    if background == PreviewBackground.WEB:
        tile = 12
        img = Image.new("RGBA", size, (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        for y in range(0, size[1], tile):
            for x in range(0, size[0], tile):
                if ((x // tile) + (y // tile)) % 2:
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(210, 210, 210, 255))
        return img
    return Image.new("RGBA", size, (245, 245, 245, 255))
