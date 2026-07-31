from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PIL import Image

from .bridge_contract import (
    CONTRACT_VERSION,
    RESULT_SCHEMA_VERSION,
    ValidatedBridgeRequest,
    sha256_path,
    tool_info,
)
from .diagnostics import analyze_alpha, utc_now_iso
from .models import ProcessingResult
from .runtime_paths import project_root


def relative_to_root(path: Path) -> str:
    root = project_root().resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("bridge artifact escaped tool root") from exc


def alpha_summary(image: Image.Image) -> dict[str, Any]:
    metrics = analyze_alpha(image.convert("RGBA"), padding=0)
    return {
        "alphaMin": metrics.alpha_min,
        "alphaMax": metrics.alpha_max,
        "fullyTransparentCount": metrics.fully_transparent_count,
        "fullyOpaqueCount": metrics.fully_opaque_count,
        "semitransparentCount": metrics.semitransparent_count,
        "transparentFraction": metrics.transparent_fraction,
        "nonopaqueFraction": metrics.nonopaque_fraction,
        "borderNonzeroCount": metrics.edge_metrics.total_border_nonzero_count,
        "borderAlphaMax": metrics.edge_metrics.border_alpha_max,
        "lowAlphaHazeSuspected": metrics.low_alpha_haze_suspected,
        "rectangularHazeSuspected": metrics.rectangular_haze_suspected,
    }


def output_manifest(
    *,
    request: ValidatedBridgeRequest,
    result: ProcessingResult,
    tool_run_id: str,
    processed_path: Path,
    events_path: Path,
    report_target: Path | None,
) -> dict[str, Any]:
    output_bytes = processed_path.stat().st_size
    report_relative = relative_to_root(report_target) if report_target else None
    return {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "contractVersion": CONTRACT_VERSION,
        "bridgeRunId": request.bridge_run_id,
        "toolRunId": tool_run_id,
        "status": "success",
        "createdAt": utc_now_iso(),
        "tool": tool_info(),
        "input": {
            "safeBasename": request.safe_basename,
            "mimeType": request.mime_type,
            "bytes": request.input_bytes,
            "sha256": request.input_sha256,
        },
        "options": {
            "mode": result.selected_mode.value,
            "aiModel": request.options.ai_model,
            "alphaMatting": request.options.alpha_matting,
            "paddingPixels": request.options.padding_pixels,
            "alphaCropThreshold": request.options.alpha_crop_threshold,
        },
        "processing": {
            "selectedRoute": result.selected_mode.value,
            "qualityVerdict": result.final_quality_result or "WARNING",
            "warnings": list(result.warnings),
            "durationMs": round(result.processing_duration * 1000, 3),
            "hazeRemovedPixelCount": result.haze_removed_pixel_count,
            "reportRelativePath": report_relative,
        },
        "output": {
            "relativePath": relative_to_root(processed_path),
            "mimeType": "image/png",
            "bytes": output_bytes,
            "sha256": sha256_path(processed_path),
            "width": result.output_image.width,
            "height": result.output_image.height,
            "alpha": alpha_summary(result.output_image),
        },
        "artifacts": {
            "eventsRelativePath": relative_to_root(events_path),
            "reportRelativePath": report_relative,
        },
        "failure": None,
    }


def failure_manifest(
    *,
    bridge_run_id: str | None,
    tool_run_id: str,
    events_path: Path,
    error_code: str,
    user_message: str,
    request: ValidatedBridgeRequest | None = None,
    report_target: Path | None = None,
) -> dict[str, Any]:
    report_relative = relative_to_root(report_target) if report_target else None
    return {
        "schemaVersion": RESULT_SCHEMA_VERSION,
        "contractVersion": CONTRACT_VERSION,
        "bridgeRunId": bridge_run_id,
        "toolRunId": tool_run_id,
        "status": "failed",
        "createdAt": utc_now_iso(),
        "tool": tool_info(),
        "input": {
            "safeBasename": request.safe_basename if request else None,
            "mimeType": request.mime_type if request else None,
            "bytes": request.input_bytes if request else None,
            "sha256": request.input_sha256 if request else None,
        },
        "options": asdict(request.options) if request else {},
        "processing": {
            "selectedRoute": None,
            "qualityVerdict": "FAIL",
            "warnings": [error_code],
            "durationMs": 0,
            "hazeRemovedPixelCount": 0,
            "reportRelativePath": report_relative,
        },
        "output": None,
        "artifacts": {
            "eventsRelativePath": relative_to_root(events_path),
            "reportRelativePath": report_relative,
        },
        "failure": {
            "code": error_code,
            "userMessage": user_message,
        },
    }


def copy_report(report_path: Path | None, target: Path) -> Path | None:
    if report_path is None:
        return None
    source = report_path if report_path.is_absolute() else project_root() / report_path
    if not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target
