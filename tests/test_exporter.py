from __future__ import annotations

import os

import pytest
from PIL import Image

from sticker_preprocessor.exporter import choose_output_path, export_png, sanitize_filename
from sticker_preprocessor.models import ExportError, InvalidOutputError
from tests.helpers import rgba_with_square


def test_output_is_png_rgba(tmp_path):
    path = export_png(rgba_with_square(), "source.jpg", tmp_path)
    with Image.open(path) as img:
        assert img.format == "PNG"
        assert img.mode == "RGBA"


def test_metadata_is_stripped(tmp_path):
    img = rgba_with_square()
    img.info["comment"] = "secret"
    path = export_png(img, "source.jpg", tmp_path)
    with Image.open(path) as reopened:
        assert "comment" not in reopened.info


def test_original_file_is_never_overwritten(tmp_path):
    original = tmp_path / "source.png"
    original.write_text("original", encoding="utf-8")
    out = export_png(rgba_with_square(), original.name, tmp_path)
    assert original.read_text(encoding="utf-8") == "original"
    assert out != original


def test_collision_generates_new_filename(tmp_path):
    first = choose_output_path("a.png", tmp_path)
    first.write_bytes(b"x")
    second = choose_output_path("a.png", tmp_path)
    assert second.name == "a_sticker_2.png"


def test_atomic_temporary_file_is_removed_on_failure(tmp_path, monkeypatch):
    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ExportError):
        export_png(rgba_with_square(), "source.jpg", tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_exported_file_reopens_successfully(tmp_path):
    path = export_png(rgba_with_square(), "source.jpg", tmp_path)
    with Image.open(path) as img:
        img.verify()


def test_export_verifies_non_opaque_alpha(tmp_path):
    with pytest.raises(InvalidOutputError):
        export_png(Image.new("RGBA", (10, 10), (1, 2, 3, 255)), "source.jpg", tmp_path)


def test_windows_invalid_filename_characters_are_sanitized():
    assert sanitize_filename('a<>:"/\\|?*b.png') == "a_________b"
