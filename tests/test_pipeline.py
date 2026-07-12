from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import sticker_preprocessor.pipeline as pipeline
from sticker_preprocessor.models import (
    AIModelError,
    CheckerboardNotDetectedError,
    InvalidOutputError,
    ProcessingMode,
    ProcessingOptions,
)
from sticker_preprocessor.pipeline import process_image
from tests.helpers import checkerboard, rgba_with_square


def test_auto_chooses_alpha_cleanup_for_real_alpha():
    result = process_image(rgba_with_square(), original_mode="RGBA", detected_format="PNG")
    assert result.selected_mode == ProcessingMode.ALPHA_CLEANUP


def test_auto_chooses_checkerboard_for_high_confidence_checker():
    result = process_image(checkerboard(subject=True), original_mode="RGB", detected_format="PNG")
    assert result.selected_mode == ProcessingMode.CHECKERBOARD


def test_auto_chooses_ai_fallback_for_opaque_non_checker_input(monkeypatch):
    def fake_remove(image, **_kwargs):
        out = image.convert("RGBA")
        arr = np.array(out)
        arr[:10, :, 3] = 0
        return Image.fromarray(arr, "RGBA")

    monkeypatch.setattr(pipeline, "remove_background", fake_remove)
    result = process_image(Image.new("RGB", (40, 40), "blue"), original_mode="RGB", detected_format="PNG")
    assert result.selected_mode == ProcessingMode.AI


def test_manual_alpha_mode_rejects_opaque_input():
    with pytest.raises(InvalidOutputError):
        process_image(
            Image.new("RGB", (40, 40), "white"),
            original_mode="RGB",
            detected_format="PNG",
            options=ProcessingOptions(mode=ProcessingMode.ALPHA_CLEANUP),
        )


def test_manual_checkerboard_mode_refuses_low_confidence():
    with pytest.raises(CheckerboardNotDetectedError):
        process_image(
            Image.new("RGB", (40, 40), "white"),
            original_mode="RGB",
            detected_format="PNG",
            options=ProcessingOptions(mode=ProcessingMode.CHECKERBOARD),
        )


def test_ai_failure_leaves_no_result(monkeypatch):
    def fake_remove(*_args, **_kwargs):
        raise AIModelError("boom")

    monkeypatch.setattr(pipeline, "remove_background", fake_remove)
    with pytest.raises(AIModelError):
        process_image(
            Image.new("RGB", (40, 40), "white"),
            original_mode="RGB",
            detected_format="PNG",
            options=ProcessingOptions(mode=ProcessingMode.AI),
        )


def test_final_invalid_all_opaque_ai_output_is_rejected(monkeypatch):
    monkeypatch.setattr(pipeline, "remove_background", lambda image, **_kwargs: image.convert("RGBA"))
    with pytest.raises(InvalidOutputError):
        process_image(
            Image.new("RGB", (40, 40), "white"),
            original_mode="RGB",
            detected_format="PNG",
            options=ProcessingOptions(mode=ProcessingMode.AI),
        )


def test_processing_result_metrics_are_correct():
    result = process_image(rgba_with_square(), original_mode="RGBA", detected_format="PNG")
    assert result.original_size == (40, 40)
    assert result.output_size == result.output_image.size
    assert result.processing_duration >= 0
