from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from sticker_preprocessor.alpha_tools import (
    GENERATED_RESULT_HAZE_CUTOFF,
    remove_border_connected_alpha_haze,
    trim_transparent_bounds,
)
from sticker_preprocessor.diagnostics import (
    QUALITY_FAIL,
    QUALITY_PASS,
    analyze_alpha,
    validate_quality,
)
from sticker_preprocessor.models import EmptyForegroundError


def test_alpha_diagnostics_histogram_buckets_and_no_pixel_array():
    values = [0, 2, 6, 12, 24, 48, 96, 160, 220, 245, 253, 255]
    img = Image.new("RGBA", (len(values), 1))
    for x, alpha in enumerate(values):
        img.putpixel((x, 0), (10, 20, 30, alpha))
    diag = analyze_alpha(img)
    assert diag.histogram.alpha_0 == 1
    assert diag.histogram.alpha_1_4 == 1
    assert diag.histogram.alpha_5_8 == 1
    assert diag.histogram.alpha_9_16 == 1
    assert diag.histogram.alpha_17_32 == 1
    assert diag.histogram.alpha_33_64 == 1
    assert diag.histogram.alpha_65_128 == 1
    assert diag.histogram.alpha_129_200 == 1
    assert diag.histogram.alpha_201_240 == 1
    assert diag.histogram.alpha_241_250 == 1
    assert diag.histogram.alpha_251_254 == 1
    assert diag.histogram.alpha_255 == 1
    assert "array" not in json.dumps(diag.__dict__, default=str).lower()


def test_threshold_bounding_boxes_edge_counts_and_corner_counts():
    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    img.putpixel((0, 0), (1, 1, 1, 5))
    ImageDraw.Draw(img).rectangle((5, 6, 12, 14), fill=(2, 3, 4, 255))
    diag = analyze_alpha(img)
    assert diag.bounding_boxes.alpha_gt_0 == (0, 0, 13, 15)
    assert diag.bounding_boxes.alpha_gt_8 == (5, 6, 13, 15)
    assert diag.edge_metrics.total_border_nonzero_count > 0
    assert diag.corner_metrics.top_left_nonzero >= 1
    assert diag.corner_metrics.maximum_corner_alpha == 255
    assert diag.nonzero_bbox_touches_frame


def test_full_frame_alpha_5_layer_is_removed():
    img = Image.new("RGBA", (20, 20), (100, 100, 100, 5))
    ImageDraw.Draw(img).rectangle((6, 6, 13, 13), fill=(255, 0, 0, 255))
    result = remove_border_connected_alpha_haze(img, threshold=8)
    assert result.removed_pixel_count > 0
    assert np.asarray(result.image.getchannel("A"))[0, :].max() == 0


def test_border_connected_alpha_8_haze_is_removed():
    img = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((0, 0, 11, 11), outline=(20, 20, 20, 8))
    ImageDraw.Draw(img).rectangle((4, 4, 7, 7), fill=(200, 0, 0, 255))
    result = remove_border_connected_alpha_haze(img, threshold=8)
    assert result.removed_pixel_count > 0
    assert result.image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_generated_route_alpha_17_32_border_haze_is_removed():
    img = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((0, 0, 11, 11), outline=(20, 20, 20, 32))
    result = remove_border_connected_alpha_haze(img, threshold=GENERATED_RESULT_HAZE_CUTOFF)
    assert result.removed_pixel_count > 0


def test_legitimate_alpha_254_subject_remains_254():
    img = Image.new("RGBA", (12, 12), (0, 0, 0, 8))
    img.putpixel((6, 6), (10, 20, 30, 254))
    result = remove_border_connected_alpha_haze(img, threshold=8)
    assert result.image.getpixel((6, 6))[3] == 254


def test_interior_low_alpha_area_not_connected_to_border_remains():
    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((6, 6, 13, 13), fill=(10, 10, 10, 8))
    result = remove_border_connected_alpha_haze(img, threshold=8)
    assert result.removed_pixel_count == 0
    assert result.image.getpixel((8, 8))[3] == 8


def test_source_image_is_unchanged_by_haze_cleanup():
    img = Image.new("RGBA", (8, 8), (1, 2, 3, 5))
    before = np.array(img)
    remove_border_connected_alpha_haze(img, threshold=8)
    assert np.array_equal(before, np.array(img))


def test_low_alpha_antialiasing_above_cutoff_remains():
    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    img.putpixel((0, 0), (1, 2, 3, 40))
    result = remove_border_connected_alpha_haze(img, threshold=32)
    assert result.image.getpixel((0, 0))[3] == 40


def test_exact_requested_transparent_padding_exists_for_edge_subject():
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((0, 0, 4, 4), fill=(255, 0, 0, 255))
    out = trim_transparent_bounds(img, padding=3)
    alpha = np.asarray(out.getchannel("A"))
    assert out.size == (11, 11)
    assert alpha[0, :].max() == 0
    assert alpha[-1, :].max() == 0
    assert alpha[:, 0].max() == 0
    assert alpha[:, -1].max() == 0


def test_no_rescaling_occurs_during_padding():
    img = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((2, 2, 3, 3), fill=(255, 0, 0, 255))
    out = trim_transparent_bounds(img, padding=2)
    assert out.size == (6, 6)
    assert np.count_nonzero(np.asarray(out.getchannel("A")) == 255) == 4


def test_quality_clean_output_passes():
    img = trim_transparent_bounds(Image.new("RGBA", (4, 4), (255, 0, 0, 255)), padding=2)
    assert validate_quality(img, padding=2, crop_threshold=8).verdict == QUALITY_PASS


def test_quality_border_nonzero_with_padding_fails():
    img = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
    img.putpixel((0, 0), (1, 2, 3, 8))
    quality = validate_quality(img, padding=2, crop_threshold=0)
    assert quality.verdict == QUALITY_FAIL
    assert "NONZERO_BORDER_WITH_PADDING" in quality.reason_codes


def test_quality_residual_rectangular_haze_fails():
    img = Image.new("RGBA", (30, 30), (10, 10, 10, 5))
    ImageDraw.Draw(img).rectangle((8, 8, 21, 21), fill=(200, 0, 0, 255))
    quality = validate_quality(img, padding=2, crop_threshold=8)
    assert quality.verdict == QUALITY_FAIL
    assert "RESIDUAL_RECTANGULAR_HAZE" in quality.reason_codes


def test_empty_foreground_fails_trim():
    with pytest.raises(EmptyForegroundError):
        trim_transparent_bounds(Image.new("RGBA", (5, 5), (0, 0, 0, 0)))


def test_all_opaque_result_fails_quality():
    quality = validate_quality(Image.new("RGBA", (5, 5), (255, 0, 0, 255)), padding=0, crop_threshold=8)
    assert quality.verdict == QUALITY_FAIL
