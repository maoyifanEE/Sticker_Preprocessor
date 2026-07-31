from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .models import InvalidOutputError, ProcessingMode
from .runtime_paths import reports_dir

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
ALPHA_SOURCE_HAZE_CUTOFF = 8
GENERATED_RESULT_HAZE_CUTOFF = 32
CORNER_PATCH_SIZE = 16
QUALITY_PASS = "PASS"
QUALITY_WARNING = "WARNING"
QUALITY_FAIL = "FAIL"


@dataclass(frozen=True)
class AlphaHistogram:
    alpha_0: int
    alpha_1_4: int
    alpha_5_8: int
    alpha_9_16: int
    alpha_17_32: int
    alpha_33_64: int
    alpha_65_128: int
    alpha_129_200: int
    alpha_201_240: int
    alpha_241_250: int
    alpha_251_254: int
    alpha_255: int


@dataclass(frozen=True)
class BoundingBoxes:
    alpha_gt_0: tuple[int, int, int, int] | None
    alpha_gt_4: tuple[int, int, int, int] | None
    alpha_gt_8: tuple[int, int, int, int] | None
    alpha_gt_16: tuple[int, int, int, int] | None
    alpha_gt_32: tuple[int, int, int, int] | None
    alpha_gt_64: tuple[int, int, int, int] | None
    alpha_gt_128: tuple[int, int, int, int] | None
    alpha_gt_250: tuple[int, int, int, int] | None
    alpha_gt_254: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class EdgeMetrics:
    top_nonzero_count: int
    bottom_nonzero_count: int
    left_nonzero_count: int
    right_nonzero_count: int
    total_border_nonzero_count: int
    border_alpha_max: int
    border_alpha_mean: float
    border_alpha_p50: float
    border_alpha_p90: float
    border_alpha_p95: float
    border_alpha_p99: float


@dataclass(frozen=True)
class CornerMetrics:
    top_left_nonzero: int
    top_right_nonzero: int
    bottom_left_nonzero: int
    bottom_right_nonzero: int
    maximum_corner_alpha: int


@dataclass(frozen=True)
class HazeDetection:
    suspected: bool
    reason_codes: tuple[str, ...]
    measured_values: dict[str, float | int | bool]


@dataclass(frozen=True)
class AlphaDiagnostics:
    width: int
    height: int
    total_pixels: int
    alpha_min: int
    alpha_max: int
    fully_transparent_count: int
    fully_opaque_count: int
    nonzero_alpha_count: int
    nonopaque_count: int
    semitransparent_count: int
    transparent_fraction: float
    nonopaque_fraction: float
    histogram: AlphaHistogram
    bounding_boxes: BoundingBoxes
    edge_metrics: EdgeMetrics
    corner_metrics: CornerMetrics
    nonzero_bbox_touches_frame: bool
    low_alpha_haze_suspected: bool
    rectangular_haze_suspected: bool
    transparent_padding_verified: bool
    haze_detection: HazeDetection


@dataclass(frozen=True)
class HazeCleanupResult:
    image: Image.Image
    removed_pixel_count: int
    threshold_used: int
    before_diagnostics: AlphaDiagnostics
    after_diagnostics: AlphaDiagnostics
    warnings: tuple[str, ...] = ()


@dataclass
class ProcessingTrace:
    schema_version: str
    run_id: str
    utc_start_time: str
    utc_finish_time: str | None
    safe_input_basename: str
    input_sha256: str | None
    source_file_size: int | None
    requested_processing_mode: str
    selected_processing_route: str | None
    selected_ai_model: str | None
    alpha_matting_enabled: bool
    crop_threshold: int
    requested_padding: int
    python_version: str
    application_version: str
    git_commit: str | None
    source_analysis: dict | None = None
    checkerboard_analysis: dict | None = None
    stage_diagnostics: dict[str, dict] = field(default_factory=dict)
    timing_breakdown: dict[str, float | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    final_quality_result: str | None = None
    failure_code: str | None = None
    report_path: str | None = None
    haze_cleanup_removed_pixels: int = 0
    haze_cleanup_threshold: int | None = None
    external_correlation_id: str | None = None
    bridge_contract_version: str | None = None
    bridge_client_name: str | None = None
    bridge_client_commit: str | None = None


@dataclass(frozen=True)
class QualityResult:
    verdict: str
    reason_codes: tuple[str, ...]
    diagnostics: AlphaDiagnostics


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex


def safe_basename(path: str | Path | None) -> str:
    if path is None:
        return "in-memory"
    return Path(path).name


def sha256_file(path: str | Path | None) -> str | None:
    if path is None:
        return None
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: str | Path) -> str:
    value = sha256_file(path)
    if value is None:
        raise ValueError("path required")
    return value


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return None


def make_trace(
    *,
    input_path: str | Path | None,
    requested_mode: ProcessingMode,
    ai_model: str | None,
    alpha_matting: bool,
    crop_threshold: int,
    padding: int,
    bridge_metadata: dict[str, str | None] | None = None,
) -> ProcessingTrace:
    file_size = Path(input_path).stat().st_size if input_path is not None and Path(input_path).is_file() else None
    try:
        digest = sha256_file(input_path)
    except OSError:
        digest = None
    metadata = bridge_metadata or {}
    return ProcessingTrace(
        schema_version=SCHEMA_VERSION,
        run_id=new_run_id(),
        utc_start_time=utc_now_iso(),
        utc_finish_time=None,
        safe_input_basename=safe_basename(input_path),
        input_sha256=digest,
        source_file_size=file_size,
        requested_processing_mode=requested_mode.value,
        selected_processing_route=None,
        selected_ai_model=ai_model,
        alpha_matting_enabled=alpha_matting,
        crop_threshold=crop_threshold,
        requested_padding=padding,
        python_version=platform.python_version(),
        application_version=__version__,
        git_commit=git_commit(),
        timing_breakdown={
            "load_seconds": None,
            "analysis_seconds": None,
            "checkerboard_seconds": None,
            "ai_initialization_seconds": None,
            "ai_inference_seconds": None,
            "alpha_cleanup_seconds": None,
            "trim_seconds": None,
            "export_seconds": None,
            "total_seconds": None,
        },
        external_correlation_id=metadata.get("external_correlation_id"),
        bridge_contract_version=metadata.get("bridge_contract_version"),
        bridge_client_name=metadata.get("bridge_client_name"),
        bridge_client_commit=metadata.get("bridge_client_commit"),
    )


def _bbox(alpha: np.ndarray, threshold: int) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(alpha > threshold)
    if not xs.size:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _touches_frame(bbox: tuple[int, int, int, int] | None, width: int, height: int) -> bool:
    return bbox is not None and (bbox[0] <= 0 or bbox[1] <= 0 or bbox[2] >= width or bbox[3] >= height)


def _meaningfully_inset(
    outer: tuple[int, int, int, int] | None,
    inner: tuple[int, int, int, int] | None,
    width: int,
    height: int,
) -> bool:
    if outer is None or inner is None:
        return False
    inset = max(2, min(width, height) // 100)
    return (
        outer[0] <= 0
        and outer[1] <= 0
        and outer[2] >= width
        and outer[3] >= height
        and (inner[0] >= inset or inner[1] >= inset or inner[2] <= width - inset or inner[3] <= height - inset)
    )


def analyze_alpha(image: Image.Image, *, padding: int = 0, haze_threshold: int = GENERATED_RESULT_HAZE_CUTOFF) -> AlphaDiagnostics:
    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    height, width = alpha.shape
    total = int(alpha.size)
    histogram = AlphaHistogram(
        alpha_0=int(np.count_nonzero(alpha == 0)),
        alpha_1_4=int(np.count_nonzero((alpha >= 1) & (alpha <= 4))),
        alpha_5_8=int(np.count_nonzero((alpha >= 5) & (alpha <= 8))),
        alpha_9_16=int(np.count_nonzero((alpha >= 9) & (alpha <= 16))),
        alpha_17_32=int(np.count_nonzero((alpha >= 17) & (alpha <= 32))),
        alpha_33_64=int(np.count_nonzero((alpha >= 33) & (alpha <= 64))),
        alpha_65_128=int(np.count_nonzero((alpha >= 65) & (alpha <= 128))),
        alpha_129_200=int(np.count_nonzero((alpha >= 129) & (alpha <= 200))),
        alpha_201_240=int(np.count_nonzero((alpha >= 201) & (alpha <= 240))),
        alpha_241_250=int(np.count_nonzero((alpha >= 241) & (alpha <= 250))),
        alpha_251_254=int(np.count_nonzero((alpha >= 251) & (alpha <= 254))),
        alpha_255=int(np.count_nonzero(alpha == 255)),
    )
    boxes = BoundingBoxes(
        alpha_gt_0=_bbox(alpha, 0),
        alpha_gt_4=_bbox(alpha, 4),
        alpha_gt_8=_bbox(alpha, 8),
        alpha_gt_16=_bbox(alpha, 16),
        alpha_gt_32=_bbox(alpha, 32),
        alpha_gt_64=_bbox(alpha, 64),
        alpha_gt_128=_bbox(alpha, 128),
        alpha_gt_250=_bbox(alpha, 250),
        alpha_gt_254=_bbox(alpha, 254),
    )
    border_values = np.concatenate((alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1]))
    nonzero_border = border_values[border_values > 0]
    if nonzero_border.size:
        p50, p90, p95, p99 = np.percentile(nonzero_border, [50, 90, 95, 99])
        border_max = int(nonzero_border.max())
        border_mean = float(nonzero_border.mean())
    else:
        p50 = p90 = p95 = p99 = border_mean = 0.0
        border_max = 0
    edge = EdgeMetrics(
        top_nonzero_count=int(np.count_nonzero(alpha[0, :] > 0)),
        bottom_nonzero_count=int(np.count_nonzero(alpha[-1, :] > 0)),
        left_nonzero_count=int(np.count_nonzero(alpha[:, 0] > 0)),
        right_nonzero_count=int(np.count_nonzero(alpha[:, -1] > 0)),
        total_border_nonzero_count=int(np.count_nonzero(border_values > 0)),
        border_alpha_max=border_max,
        border_alpha_mean=border_mean,
        border_alpha_p50=float(p50),
        border_alpha_p90=float(p90),
        border_alpha_p95=float(p95),
        border_alpha_p99=float(p99),
    )
    patch = min(CORNER_PATCH_SIZE, width, height)
    corners = (
        alpha[:patch, :patch],
        alpha[:patch, width - patch :],
        alpha[height - patch :, :patch],
        alpha[height - patch :, width - patch :],
    )
    corner = CornerMetrics(
        top_left_nonzero=int(np.count_nonzero(corners[0] > 0)),
        top_right_nonzero=int(np.count_nonzero(corners[1] > 0)),
        bottom_left_nonzero=int(np.count_nonzero(corners[2] > 0)),
        bottom_right_nonzero=int(np.count_nonzero(corners[3] > 0)),
        maximum_corner_alpha=int(max(int(c.max()) for c in corners)) if corners else 0,
    )
    nonzero_touches = _touches_frame(boxes.alpha_gt_0, width, height)
    inner = boxes.alpha_gt_8 if haze_threshold <= 8 else boxes.alpha_gt_32
    bbox_divergence = _meaningfully_inset(boxes.alpha_gt_0, inner, width, height)
    low_alpha_border = edge.total_border_nonzero_count > 4 and edge.border_alpha_max <= haze_threshold
    low_alpha_corners = (
        corner.maximum_corner_alpha > 0
        and corner.maximum_corner_alpha <= haze_threshold
        and sum(
            count > 0
            for count in (
                corner.top_left_nonzero,
                corner.top_right_nonzero,
                corner.bottom_left_nonzero,
                corner.bottom_right_nonzero,
            )
        )
        >= 2
    )
    rectangular = bool(nonzero_touches and bbox_divergence and (low_alpha_border or low_alpha_corners))
    reasons: list[str] = []
    if nonzero_touches:
        reasons.append("NONZERO_ALPHA_TOUCHES_FRAME")
    if low_alpha_border:
        reasons.append("LOW_ALPHA_BORDER_CONNECTION")
    if low_alpha_corners:
        reasons.append("LOW_ALPHA_CORNERS")
    if bbox_divergence:
        reasons.append("THRESHOLD_BBOX_DIVERGENCE")
    if rectangular:
        reasons.append("LARGE_RECTANGULAR_LOW_ALPHA_REGION")
    haze = HazeDetection(
        suspected=bool(rectangular or (low_alpha_border and bbox_divergence)),
        reason_codes=tuple(reasons),
        measured_values={
            "border_nonzero": edge.total_border_nonzero_count,
            "border_alpha_max": edge.border_alpha_max,
            "corner_alpha_max": corner.maximum_corner_alpha,
            "nonzero_touches_frame": nonzero_touches,
            "bbox_divergence": bbox_divergence,
        },
    )
    return AlphaDiagnostics(
        width=width,
        height=height,
        total_pixels=total,
        alpha_min=int(alpha.min()),
        alpha_max=int(alpha.max()),
        fully_transparent_count=histogram.alpha_0,
        fully_opaque_count=histogram.alpha_255,
        nonzero_alpha_count=int(np.count_nonzero(alpha > 0)),
        nonopaque_count=int(np.count_nonzero(alpha < 255)),
        semitransparent_count=int(np.count_nonzero((alpha > 0) & (alpha < 255))),
        transparent_fraction=histogram.alpha_0 / total,
        nonopaque_fraction=int(np.count_nonzero(alpha < 255)) / total,
        histogram=histogram,
        bounding_boxes=boxes,
        edge_metrics=edge,
        corner_metrics=corner,
        nonzero_bbox_touches_frame=nonzero_touches,
        low_alpha_haze_suspected=haze.suspected,
        rectangular_haze_suspected=rectangular,
        transparent_padding_verified=padding <= 0 or edge.total_border_nonzero_count == 0,
        haze_detection=haze,
    )


def dataclass_to_dict(value: object) -> dict:
    return asdict(value)  # type: ignore[arg-type]


def trace_to_dict(trace: ProcessingTrace) -> dict:
    data = asdict(trace)
    return data


def write_trace_report(trace: ProcessingTrace) -> Path | None:
    try:
        trace.utc_finish_time = trace.utc_finish_time or utc_now_iso()
        directory = reports_dir()
        directory.mkdir(parents=True, exist_ok=True)
        final_path = directory / f"{trace.run_id}.json"
        tmp_path = final_path.with_suffix(".json.tmp")
        trace.report_path = str(final_path.relative_to(Path(__file__).resolve().parents[2]))
        tmp_path.write_text(json.dumps(trace_to_dict(trace), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, final_path)
        LOGGER.info("run.report_written run_id=%s report=%s", trace.run_id, final_path.name)
        return final_path
    except Exception:
        LOGGER.exception("run.report_write_failed run_id=%s", trace.run_id)
        return None


def log_event(event: str, *, run_id: str | None = None, **metrics: object) -> None:
    safe = " ".join(f"{key}={value}" for key, value in metrics.items())
    LOGGER.info("%s run_id=%s %s", event, run_id or "-", safe)


def validate_quality(image: Image.Image, *, padding: int, crop_threshold: int) -> QualityResult:
    if image.mode != "RGBA":
        diagnostics = analyze_alpha(image.convert("RGBA"), padding=padding)
        return QualityResult(QUALITY_FAIL, ("NOT_RGBA",), diagnostics)
    diagnostics = analyze_alpha(image, padding=padding)
    reasons: list[str] = []
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    if diagnostics.alpha_min >= 255:
        reasons.append("NO_TRANSPARENCY")
    if diagnostics.fully_transparent_count <= 0:
        reasons.append("NO_FULLY_TRANSPARENT_PIXELS")
    if diagnostics.width < 1 or diagnostics.height < 1:
        reasons.append("INVALID_DIMENSIONS")
    if not np.any(alpha > crop_threshold):
        reasons.append("EMPTY_FOREGROUND")
    if padding > 0 and diagnostics.edge_metrics.total_border_nonzero_count != 0:
        reasons.append("NONZERO_BORDER_WITH_PADDING")
    if diagnostics.rectangular_haze_suspected:
        reasons.append("RESIDUAL_RECTANGULAR_HAZE")
    arr = np.asarray(image)
    transparent_rgb_dirty = bool(np.any(arr[arr[:, :, 3] == 0, :3] != 0))
    if transparent_rgb_dirty:
        reasons.append("TRANSPARENT_RGB_NOT_ZERO")
    verdict = QUALITY_FAIL if reasons else QUALITY_PASS
    return QualityResult(verdict, tuple(reasons), diagnostics)


class ResidualAlphaHazeError(InvalidOutputError):
    code = "RESIDUAL_ALPHA_HAZE"
    user_message = "处理结果仍包含可能形成矩形边框的半透明背景，请查看诊断报告或更换处理模式。"
