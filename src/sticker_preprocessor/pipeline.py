from __future__ import annotations

import logging
import time

import numpy as np
from PIL import Image

from .alpha_tools import trim_transparent_bounds
from .analyzer import analyze_image
from .checkerboard import analyze_checkerboard, remove_checkerboard
from .models import (
    CheckerboardAnalysis,
    CheckerboardNotDetectedError,
    InvalidOutputError,
    ProcessingMode,
    ProcessingOptions,
    ProcessingResult,
)
from .rembg_adapter import remove_background

LOGGER = logging.getLogger(__name__)


def _transparent_fraction(image: Image.Image) -> float:
    alpha = np.asarray(image.convert("RGBA").getchannel("A"), dtype=np.uint8)
    return float(np.count_nonzero(alpha < 255) / alpha.size)


def _validate_transparent_output(image: Image.Image) -> None:
    if image.mode != "RGBA":
        raise InvalidOutputError()
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    if int(np.count_nonzero(alpha < 250)) == 0:
        raise InvalidOutputError("输出结果没有真实透明像素。")


def process_image(
    image: Image.Image,
    *,
    original_mode: str = "RGBA",
    detected_format: str = "PNG",
    options: ProcessingOptions | None = None,
) -> ProcessingResult:
    opts = options or ProcessingOptions()
    start = time.perf_counter()
    source = image.convert("RGBA")
    analysis = analyze_image(source, original_mode=original_mode, detected_format=detected_format)
    checker: CheckerboardAnalysis | None = None
    selected = opts.mode
    LOGGER.info("processing_started mode=%s width=%s height=%s", opts.mode.value, source.width, source.height)

    if opts.mode == ProcessingMode.AUTO:
        if analysis.meaningful_transparency:
            selected = ProcessingMode.ALPHA_CLEANUP
        else:
            checker = analyze_checkerboard(source)
            selected = ProcessingMode.CHECKERBOARD if checker.detected else ProcessingMode.AI

    if selected == ProcessingMode.ALPHA_CLEANUP:
        if not analysis.meaningful_transparency:
            raise InvalidOutputError("此图片没有可清理的真实透明背景。")
        LOGGER.info("selected_processing_route route=alpha_cleanup")
        output = trim_transparent_bounds(
            source,
            alpha_threshold=opts.alpha_crop_threshold,
            padding=opts.padding_pixels,
        )
    elif selected == ProcessingMode.CHECKERBOARD:
        checker = checker or analyze_checkerboard(source)
        if not checker.detected:
            raise CheckerboardNotDetectedError()
        LOGGER.info("selected_processing_route route=checkerboard confidence=%.3f", checker.confidence)
        output, checker = remove_checkerboard(
            source,
            checker,
            padding=opts.padding_pixels,
            alpha_threshold=opts.alpha_crop_threshold,
        )
    elif selected == ProcessingMode.AI:
        LOGGER.info("selected_processing_route route=ai model=%s", opts.ai_model)
        ai_output = remove_background(source, model_name=opts.ai_model, alpha_matting=opts.alpha_matting)
        output = trim_transparent_bounds(
            ai_output,
            alpha_threshold=opts.alpha_crop_threshold,
            padding=opts.padding_pixels,
        )
    else:
        raise InvalidOutputError("未知处理模式。")

    _validate_transparent_output(output)
    duration = time.perf_counter() - start
    result = ProcessingResult(
        output_image=output,
        selected_mode=selected,
        source_analysis=analysis,
        checkerboard_analysis=checker,
        original_size=source.size,
        output_size=output.size,
        transparent_fraction=_transparent_fraction(output),
        processing_duration=duration,
        warnings=(),
    )
    LOGGER.info(
        "processing_succeeded mode=%s output=%sx%s duration=%.3f",
        result.selected_mode.value,
        result.output_size[0],
        result.output_size[1],
        duration,
    )
    return result
