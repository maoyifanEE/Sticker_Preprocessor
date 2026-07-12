from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sticker_preprocessor.checkerboard import analyze_checkerboard, remove_checkerboard
from sticker_preprocessor.models import CheckerboardNotDetectedError
from tests.helpers import checkerboard


def test_8_pixel_synthetic_two_color_checker_detected():
    result = analyze_checkerboard(checkerboard(tile=8))
    assert result.detected
    assert result.estimated_tile_size == 8


def test_16_pixel_checker_detected():
    result = analyze_checkerboard(checkerboard(tile=16, width=128, height=128))
    assert result.detected
    assert result.estimated_tile_size == 16


def test_24_pixel_checker_detected():
    result = analyze_checkerboard(checkerboard(tile=24, width=144, height=144))
    assert result.detected
    assert result.estimated_tile_size == 24


def test_shifted_parity_detected():
    result = analyze_checkerboard(checkerboard(tile=8, shift=(4, 4)))
    assert result.detected
    assert result.phase is not None


@pytest.mark.parametrize("shift", [(1, 1), (2, 5), (3, 7), (7, 2)])
def test_tile_8_arbitrary_offsets_remove_border_background(shift):
    out, analysis = remove_checkerboard(checkerboard(tile=8, shift=shift, subject=True))
    alpha = np.asarray(out.getchannel("A"))
    assert analysis.detected
    assert alpha.min() == 0
    assert alpha.max() == 255


@pytest.mark.parametrize("shift", [(1, 9), (15, 4)])
def test_tile_16_arbitrary_offsets_remove_border_background(shift):
    out, analysis = remove_checkerboard(checkerboard(width=128, height=112, tile=16, shift=shift, subject=True))
    alpha = np.asarray(out.getchannel("A"))
    assert analysis.detected
    assert alpha.min() == 0
    assert alpha.max() == 255


def test_non_square_checkerboard_dimensions_remove_correctly():
    out, analysis = remove_checkerboard(
        checkerboard(width=137, height=91, tile=8, shift=(5, 3), subject=True),
        padding=0,
    )
    assert analysis.detected
    assert out.size[0] < 137
    assert out.size[1] < 91


def test_checkerboard_cropped_from_all_four_sides_removes_correctly():
    cropped = checkerboard(width=140, height=130, tile=8, shift=(6, 2), subject=True).crop((3, 5, 133, 121))
    out, analysis = remove_checkerboard(cropped)
    alpha = np.asarray(out.getchannel("A"))
    assert analysis.detected
    assert alpha.min() == 0
    assert alpha.max() == 255


def test_mild_rgb_noise_tolerated():
    result = analyze_checkerboard(checkerboard(tile=8, noise=2))
    assert result.detected


def test_central_subject_does_not_break_border_detection():
    result = analyze_checkerboard(checkerboard(tile=8, subject=True))
    assert result.detected


def test_ordinary_solid_white_background_not_checkerboard():
    result = analyze_checkerboard(Image.new("RGBA", (80, 80), (255, 255, 255, 255)))
    assert not result.detected


def test_grayscale_gradient_not_checkerboard():
    img = Image.new("RGB", (80, 80))
    for x in range(80):
        for y in range(80):
            img.putpixel((x, y), (180 + x // 2, 180 + x // 2, 180 + x // 2))
    assert not analyze_checkerboard(img.convert("RGBA")).detected


def test_real_grid_like_subject_with_non_border_dominant_pattern_rejected():
    img = Image.new("RGB", (96, 96), "white")
    draw = ImageDraw.Draw(img)
    for x in range(20, 80, 8):
        draw.line((x, 20, x, 80), fill=(210, 210, 210), width=1)
    for y in range(20, 80, 8):
        draw.line((20, y, 80, y), fill=(210, 210, 210), width=1)
    assert not analyze_checkerboard(img.convert("RGBA")).detected


def test_low_confidence_result_is_not_processed():
    with pytest.raises(CheckerboardNotDetectedError):
        remove_checkerboard(Image.new("RGBA", (80, 80), (255, 255, 255, 255)))


def test_border_connected_checker_becomes_transparent():
    out, analysis = remove_checkerboard(checkerboard(tile=8, subject=True))
    assert analysis.detected
    assert np.asarray(out.getchannel("A")).min() == 0


def test_central_synthetic_subject_remains():
    out, _ = remove_checkerboard(checkerboard(tile=8, subject=True))
    alpha = np.asarray(out.getchannel("A"))
    assert alpha.max() == 255
    assert np.count_nonzero(alpha == 255) > 100


def test_enclosed_similar_colored_subject_area_not_removed_solely_by_color():
    out, _ = remove_checkerboard(checkerboard(tile=8, subject=True))
    arr = np.asarray(out)
    similar_visible = (arr[:, :, 0] > 230) & (arr[:, :, 1] > 230) & (arr[:, :, 2] > 230) & (arr[:, :, 3] > 0)
    assert np.any(similar_visible)


def test_result_contains_real_alpha():
    out, _ = remove_checkerboard(checkerboard(tile=8, subject=True))
    assert np.count_nonzero(np.asarray(out.getchannel("A")) < 250) > 0


def test_result_trims_correctly():
    out, _ = remove_checkerboard(checkerboard(tile=8, subject=True), padding=0)
    assert out.size[0] < 96
    assert out.size[1] < 96


def test_input_image_is_unchanged():
    img = checkerboard(tile=8, subject=True)
    before = np.array(img)
    remove_checkerboard(img)
    assert np.array_equal(before, np.array(img))
