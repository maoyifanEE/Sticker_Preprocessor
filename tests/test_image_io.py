from __future__ import annotations

import pytest
from PIL import Image

from sticker_preprocessor.image_io import load_image
from sticker_preprocessor.models import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedFormatError,
)


def test_valid_png_loads(tmp_path):
    path = tmp_path / "a.png"
    Image.new("RGBA", (8, 8), (1, 2, 3, 4)).save(path)
    loaded = load_image(path)
    assert loaded.detected_format == "PNG"
    assert loaded.image.mode == "RGBA"


def test_valid_jpeg_loads(tmp_path):
    path = tmp_path / "a.jpg"
    Image.new("RGB", (8, 8), "white").save(path)
    assert load_image(path).detected_format == "JPEG"


def test_valid_webp_loads_when_supported(tmp_path):
    features = pytest.importorskip("PIL.features")
    if not features.check("webp"):
        pytest.skip("WebP unsupported by this Pillow build")
    path = tmp_path / "a.webp"
    Image.new("RGB", (8, 8), "white").save(path)
    assert load_image(path).detected_format == "WEBP"


def test_malformed_file_rejected(tmp_path):
    path = tmp_path / "bad.png"
    path.write_bytes(b"not an image")
    with pytest.raises(InvalidImageError):
        load_image(path)


def test_unsupported_format_rejected(tmp_path):
    path = tmp_path / "a.bmp"
    Image.new("RGB", (8, 8), "white").save(path)
    with pytest.raises(UnsupportedFormatError):
        load_image(path)


def test_animated_input_rejected(tmp_path):
    path = tmp_path / "a.gif"
    Image.new("RGB", (8, 8), "white").save(
        path, save_all=True, append_images=[Image.new("RGB", (8, 8), "black")]
    )
    with pytest.raises(UnsupportedFormatError):
        load_image(path)


def test_dimension_limit_rejected(monkeypatch, tmp_path):
    import sticker_preprocessor.image_io as image_io

    monkeypatch.setattr(image_io, "MAX_DIMENSION", 4)
    path = tmp_path / "big.png"
    Image.new("RGB", (8, 8), "white").save(path)
    with pytest.raises(ImageTooLargeError):
        load_image(path)


def test_pixel_limit_rejected(monkeypatch, tmp_path):
    import sticker_preprocessor.image_io as image_io

    monkeypatch.setattr(image_io, "MAX_PIXELS", 20)
    path = tmp_path / "many.png"
    Image.new("RGB", (8, 8), "white").save(path)
    with pytest.raises(ImageTooLargeError):
        load_image(path)


def test_exif_orientation_applied(tmp_path):
    path = tmp_path / "rotated.jpg"
    img = Image.new("RGB", (10, 20), "white")
    exif = Image.Exif()
    exif[274] = 6
    img.save(path, exif=exif)
    loaded = load_image(path)
    assert loaded.image.size == (20, 10)


def test_file_size_limit_rejected(monkeypatch, tmp_path):
    import sticker_preprocessor.image_io as image_io

    monkeypatch.setattr(image_io, "MAX_FILE_SIZE", 3)
    path = tmp_path / "small.png"
    Image.new("RGB", (8, 8), "white").save(path)
    with pytest.raises(ImageTooLargeError):
        load_image(path)


def test_decompression_bomb_error_becomes_image_too_large(monkeypatch, tmp_path):
    from PIL import Image as PilImage

    path = tmp_path / "bomb.png"
    path.write_bytes(b"not actually decoded")

    def raise_bomb(_path):
        raise PilImage.DecompressionBombError("raw internal detail")

    monkeypatch.setattr("sticker_preprocessor.image_io.Image.open", raise_bomb)
    with pytest.raises(ImageTooLargeError) as exc_info:
        load_image(path)
    assert str(exc_info.value) == ImageTooLargeError.user_message
