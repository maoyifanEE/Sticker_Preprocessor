from __future__ import annotations

import numpy as np
from PIL import Image

from sticker_preprocessor.models import PreviewBackground
from sticker_preprocessor.preview import (
    DARK_BACKGROUND,
    LIGHT_BACKGROUND,
    _background,
    make_preview,
)


def test_light_produces_expected_solid_background():
    bg = _background((6, 4), PreviewBackground.LIGHT)
    arr = np.asarray(bg)
    assert np.all(arr == np.array(LIGHT_BACKGROUND, dtype=np.uint8))


def test_dark_produces_expected_solid_background():
    bg = _background((6, 4), PreviewBackground.DARK)
    arr = np.asarray(bg)
    assert np.all(arr == np.array(DARK_BACKGROUND, dtype=np.uint8))


def test_web_is_gradient_and_not_repeating_checker_pattern():
    bg = _background((24, 24), PreviewBackground.WEB).convert("RGB")
    arr = np.asarray(bg)
    assert not np.array_equal(arr[0, 0], arr[-1, -1])
    assert not np.array_equal(arr[0:12, 0:12], arr[12:24, 12:24])


def test_transparent_output_reveals_selected_background():
    transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    preview = make_preview(transparent, PreviewBackground.LIGHT, (4, 4))
    assert np.all(np.asarray(preview.convert("RGBA")) == np.array(LIGHT_BACKGROUND, dtype=np.uint8))


def test_opaque_input_does_not_falsely_appear_transparent():
    opaque = Image.new("RGBA", (4, 4), (10, 20, 30, 255))
    preview = make_preview(opaque, PreviewBackground.LIGHT, (4, 4))
    assert np.all(np.asarray(preview) == np.array((10, 20, 30), dtype=np.uint8))
