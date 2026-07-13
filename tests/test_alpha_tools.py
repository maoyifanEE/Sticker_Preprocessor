from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sticker_preprocessor.alpha_tools import clear_rgb_where_alpha_zero, trim_transparent_bounds
from sticker_preprocessor.models import EmptyForegroundError
from tests.helpers import rgba_with_square


def test_transparent_margins_are_cropped():
    out = trim_transparent_bounds(rgba_with_square(), padding=0)
    assert out.size == (20, 20)


def test_padding_is_retained():
    out = trim_transparent_bounds(rgba_with_square(), padding=2)
    assert out.size == (24, 24)


def test_padding_is_clamped_to_bounds():
    out = trim_transparent_bounds(rgba_with_square(size=20, margin=1), padding=20)
    assert out.size == (58, 58)
    assert np.asarray(out.getchannel("A"))[0, :].max() == 0


def test_semitransparent_pixels_are_preserved():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    img.putpixel((5, 5), (10, 20, 30, 128))
    out = trim_transparent_bounds(img, alpha_threshold=8, padding=0)
    assert out.getpixel((0, 0))[3] == 128


def test_fully_transparent_rgb_is_cleared_safely():
    img = Image.new("RGBA", (2, 1), (200, 100, 50, 0))
    img.putpixel((1, 0), (1, 2, 3, 255))
    out = clear_rgb_where_alpha_zero(img)
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)
    assert out.getpixel((1, 0)) == (1, 2, 3, 255)


def test_empty_foreground_raises_expected_error():
    with pytest.raises(EmptyForegroundError):
        trim_transparent_bounds(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))


def test_source_image_object_is_not_mutated():
    img = rgba_with_square()
    before = np.array(img)
    trim_transparent_bounds(img, padding=0)
    assert np.array_equal(before, np.array(img))


def test_threshold_uses_foreground_above_value():
    img = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    ImageDraw.Draw(img).point((2, 2), fill=(1, 2, 3, 7))
    with pytest.raises(EmptyForegroundError):
        trim_transparent_bounds(img, alpha_threshold=8)
