from __future__ import annotations

import random

from PIL import Image, ImageDraw


def rgba_with_square(size: int = 40, margin: int = 10) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((margin, margin, size - margin - 1, size - margin - 1), fill=(20, 120, 220, 255))
    return img


def checkerboard(
    width: int = 96,
    height: int = 96,
    tile: int = 8,
    shift: tuple[int, int] = (0, 0),
    noise: int = 0,
    subject: bool = False,
) -> Image.Image:
    colors = ((204, 204, 204), (238, 238, 238))
    img = Image.new("RGB", (width, height))
    pixels = img.load()
    rnd = random.Random(7)
    for y in range(height):
        for x in range(width):
            idx = (((x + shift[0]) // tile) + ((y + shift[1]) // tile)) % 2
            color = list(colors[idx])
            if noise:
                color = [max(0, min(255, c + rnd.randint(-noise, noise))) for c in color]
            pixels[x, y] = tuple(color)
    if subject:
        draw = ImageDraw.Draw(img)
        draw.rectangle((30, 25, 68, 72), fill=(200, 40, 80))
        draw.ellipse((42, 38, 56, 54), fill=(238, 238, 238))
    return img.convert("RGBA")
