from __future__ import annotations

import logging
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from .alpha_tools import (
    haze_threshold_for_route,
    remove_border_connected_alpha_haze,
    trim_transparent_bounds,
)
from .analyzer import analyze_image
from .checkerboard import analyze_checkerboard, remove_checkerboard
from .diagnostics import (
    QUALITY_FAIL,
    ResidualAlphaHazeError,
    analyze_alpha,
    log_event,
    make_trace,
    validate_quality,
    write_trace_report,
)
from .models import (
    CheckerboardAnalysis,
    CheckerboardNotDetectedError,
    InvalidOutputError,
    ProcessingMode,
    ProcessingOptions,
    ProcessingResult,
    StickerPreprocessorError,
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
    input_path: str | Path | None = None,
    bridge_metadata: dict[str, str | None] | None = None,
) -> ProcessingResult:
    opts = options or ProcessingOptions()
    trace = make_trace(
        input_path=input_path,
        requested_mode=opts.mode,
        ai_model=opts.ai_model,
        alpha_matting=opts.alpha_matting,
        crop_threshold=opts.alpha_crop_threshold,
        padding=opts.padding_pixels,
        bridge_metadata=bridge_metadata,
    )
    start_total = time.perf_counter()
    checker: CheckerboardAnalysis | None = None
    selected = opts.mode
    output: Image.Image | None = None
    haze_removed = 0
    report_path: Path | None = None
    log_event("run.started", run_id=trace.run_id, mode=opts.mode.value, model=opts.ai_model)
    try:
        source = image.convert("RGBA")
        trace.stage_diagnostics["source"] = asdict(analyze_alpha(source, padding=0))
        LOGGER.info("alpha.stage_measured run_id=%s stage=source", trace.run_id)

        t0 = time.perf_counter()
        analysis = analyze_image(source, original_mode=original_mode, detected_format=detected_format)
        trace.timing_breakdown["analysis_seconds"] = time.perf_counter() - t0
        trace.source_analysis = asdict(analysis)
        log_event("input.analysis_completed", run_id=trace.run_id, width=analysis.width, height=analysis.height)
        LOGGER.info("processing_started run_id=%s mode=%s width=%s height=%s", trace.run_id, opts.mode.value, source.width, source.height)

        if opts.mode == ProcessingMode.AUTO:
            if analysis.meaningful_transparency:
                selected = ProcessingMode.ALPHA_CLEANUP
            else:
                t0 = time.perf_counter()
                checker = analyze_checkerboard(source)
                trace.timing_breakdown["checkerboard_seconds"] = time.perf_counter() - t0
                trace.checkerboard_analysis = asdict(checker)
                log_event(
                    "checkerboard.analysis_completed",
                    run_id=trace.run_id,
                    detected=checker.detected,
                    confidence=round(checker.confidence, 4),
                )
                selected = ProcessingMode.CHECKERBOARD if checker.detected else ProcessingMode.AI

        trace.selected_processing_route = selected.value
        log_event("route.selected", run_id=trace.run_id, route=selected.value)

        if selected == ProcessingMode.ALPHA_CLEANUP:
            if not analysis.meaningful_transparency:
                raise InvalidOutputError("此图片没有可清理的真实透明背景。")
            LOGGER.info("selected_processing_route run_id=%s route=alpha_cleanup", trace.run_id)
            route_output = source
        elif selected == ProcessingMode.CHECKERBOARD:
            checker = checker or analyze_checkerboard(source)
            trace.checkerboard_analysis = asdict(checker)
            if not checker.detected:
                raise CheckerboardNotDetectedError()
            LOGGER.info("selected_processing_route run_id=%s route=checkerboard confidence=%.3f", trace.run_id, checker.confidence)
            route_output, checker = remove_checkerboard(
                source,
                checker,
                padding=0,
                alpha_threshold=opts.alpha_crop_threshold,
            )
        elif selected == ProcessingMode.AI:
            LOGGER.info("selected_processing_route run_id=%s route=ai model=%s", trace.run_id, opts.ai_model)
            t0 = time.perf_counter()
            ai_output = remove_background(source, model_name=opts.ai_model, alpha_matting=opts.alpha_matting)
            trace.timing_breakdown["ai_inference_seconds"] = time.perf_counter() - t0
            route_output = ai_output
        else:
            raise InvalidOutputError("未知处理模式。")

        trace.stage_diagnostics["route_output_before_cleanup"] = asdict(
            analyze_alpha(route_output, padding=0, haze_threshold=haze_threshold_for_route(selected.value))
        )
        LOGGER.info("alpha.stage_measured run_id=%s stage=route_output_before_cleanup", trace.run_id)

        t0 = time.perf_counter()
        threshold = haze_threshold_for_route(selected.value)
        force_cleanup = selected != ProcessingMode.ALPHA_CLEANUP or trace.stage_diagnostics["route_output_before_cleanup"]["low_alpha_haze_suspected"]
        cleanup = remove_border_connected_alpha_haze(
            route_output,
            threshold=threshold,
            padding=0,
            force=force_cleanup,
        )
        trace.timing_breakdown["alpha_cleanup_seconds"] = time.perf_counter() - t0
        trace.haze_cleanup_removed_pixels = cleanup.removed_pixel_count
        trace.haze_cleanup_threshold = cleanup.threshold_used
        haze_removed = cleanup.removed_pixel_count
        trace.stage_diagnostics["after_alpha_haze_cleanup"] = asdict(cleanup.after_diagnostics)
        cleanup_alpha = np.asarray(cleanup.image.getchannel("A"), dtype=np.uint8)
        if selected == ProcessingMode.AI and int(np.count_nonzero(cleanup_alpha < 250)) == 0:
            raise InvalidOutputError("输出结果没有真实透明像素。")
        if cleanup.removed_pixel_count:
            log_event("alpha.haze_detected", run_id=trace.run_id, removed_pixels=cleanup.removed_pixel_count, threshold=threshold)
        log_event("alpha.haze_cleanup_succeeded", run_id=trace.run_id, removed_pixels=cleanup.removed_pixel_count, threshold=threshold)

        t0 = time.perf_counter()
        output = trim_transparent_bounds(
            cleanup.image,
            alpha_threshold=opts.alpha_crop_threshold,
            padding=opts.padding_pixels,
        )
        trace.timing_breakdown["trim_seconds"] = time.perf_counter() - t0
        after_trim = analyze_alpha(output, padding=opts.padding_pixels, haze_threshold=threshold)
        trace.stage_diagnostics["after_trim"] = asdict(after_trim)
        trace.stage_diagnostics["final_export_candidate"] = asdict(after_trim)
        log_event("alpha.trim_completed", run_id=trace.run_id, border_nonzero=after_trim.edge_metrics.total_border_nonzero_count)

        _validate_transparent_output(output)
        quality = validate_quality(output, padding=opts.padding_pixels, crop_threshold=opts.alpha_crop_threshold)
        trace.final_quality_result = quality.verdict
        if quality.verdict == QUALITY_FAIL:
            trace.warnings.extend(quality.reason_codes)
            log_event("quality.validation_failed", run_id=trace.run_id, reasons=",".join(quality.reason_codes))
            if "RESIDUAL_RECTANGULAR_HAZE" in quality.reason_codes:
                raise ResidualAlphaHazeError()
            raise InvalidOutputError("输出结果未通过透明质量检查。")
        log_event("quality.validation_passed", run_id=trace.run_id, verdict=quality.verdict)

        duration = time.perf_counter() - start_total
        trace.timing_breakdown["total_seconds"] = duration
        result = ProcessingResult(
            output_image=output,
            selected_mode=selected,
            source_analysis=analysis,
            checkerboard_analysis=checker,
            original_size=source.size,
            output_size=output.size,
            transparent_fraction=_transparent_fraction(output),
            processing_duration=duration,
            warnings=tuple(trace.warnings),
            run_id=trace.run_id,
            final_quality_result=trace.final_quality_result,
            haze_removed_pixel_count=haze_removed,
            final_border_nonzero_count=quality.diagnostics.edge_metrics.total_border_nonzero_count,
            alpha_gt_0_bbox=quality.diagnostics.bounding_boxes.alpha_gt_0,
            alpha_gt_8_bbox=quality.diagnostics.bounding_boxes.alpha_gt_8,
        )
        trace.utc_finish_time = trace.utc_finish_time or None
        report_path = write_trace_report(trace)
        result = ProcessingResult(
            **{**result.__dict__, "report_path": report_path}
        )
        LOGGER.info(
            "run.completed run_id=%s mode=%s output=%sx%s duration=%.3f quality=%s",
            trace.run_id,
            result.selected_mode.value,
            result.output_size[0],
            result.output_size[1],
            duration,
            result.final_quality_result,
        )
        return result
    except StickerPreprocessorError as exc:
        trace.failure_code = exc.code
        trace.final_quality_result = trace.final_quality_result or QUALITY_FAIL
        trace.timing_breakdown["total_seconds"] = time.perf_counter() - start_total
        report_path = write_trace_report(trace)
        exc.run_id = trace.run_id
        exc.report_path = report_path
        log_event("run.failed", run_id=trace.run_id, error_code=exc.code)
        raise
    except Exception as exc:
        trace.failure_code = "UNEXPECTED_ERROR"
        trace.final_quality_result = QUALITY_FAIL
        trace.timing_breakdown["total_seconds"] = time.perf_counter() - start_total
        report_path = write_trace_report(trace)
        LOGGER.exception("run.failed run_id=%s error_code=UNEXPECTED_ERROR", trace.run_id)
        wrapped = InvalidOutputError("处理失败，请查看本地日志。")
        wrapped.run_id = trace.run_id
        wrapped.report_path = report_path
        raise wrapped from exc
