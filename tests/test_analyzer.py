from __future__ import annotations

from PIL import Image, ImageDraw

from sticker_preprocessor.analyzer import analyze_image


def test_fully_opaque_rgb_reports_no_transparency():
    result = analyze_image(Image.new("RGB", (20, 20), "white"), original_mode="RGB", detected_format="PNG")
    assert not result.has_source_alpha_channel
    assert not result.meaningful_transparency


def test_rgba_alpha_all_255_reports_no_real_transparency():
    result = analyze_image(Image.new("RGBA", (20, 20), (1, 2, 3, 255)), original_mode="RGBA", detected_format="PNG")
    assert result.has_source_alpha_channel
    assert not result.meaningful_transparency


def test_rgba_transparent_border_reports_meaningful_transparency():
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((10, 10, 29, 29), fill=(255, 0, 0, 255))
    result = analyze_image(img, original_mode="RGBA", detected_format="PNG")
    assert result.meaningful_transparency
    assert result.fully_transparent_count > 0


def test_semitransparent_edges_are_counted():
    img = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    ImageDraw.Draw(img).rectangle((0, 0, 19, 0), fill=(255, 0, 0, 128))
    result = analyze_image(img, original_mode="RGBA", detected_format="PNG")
    assert result.semitransparent_count == 20


def test_alpha_bbox_is_correct():
    img = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((5, 6, 12, 14), fill=(0, 0, 0, 255))
    result = analyze_image(img, original_mode="RGBA", detected_format="PNG")
    assert result.alpha_bbox == (5, 6, 13, 15)


def test_trivial_single_stray_transparent_pixel_not_meaningful():
    img = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
    img.putpixel((0, 0), (255, 255, 255, 0))
    result = analyze_image(img, original_mode="RGBA", detected_format="PNG")
    assert not result.meaningful_transparency
    assert result.nonopaque_count == 1
