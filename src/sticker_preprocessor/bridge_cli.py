from __future__ import annotations

import contextlib
import io
import time
from pathlib import Path

from .bridge_contract import (
    BridgeContractError,
    capabilities,
    compact_json,
    exit_code_for_error,
    load_request,
    response,
    validate_request,
)
from .bridge_events import BridgeEventWriter, bridge_runs_root, prune_bridge_runs, write_json_atomic
from .bridge_manifest import copy_report, failure_manifest, output_manifest, relative_to_root
from .diagnostics import new_run_id
from .exporter import export_png_to_path
from .image_io import load_image
from .pipeline import process_image


def run_capabilities() -> int:
    print(compact_json(capabilities()))
    return 0


def _sanitized_request(request) -> dict:
    return {
        "schemaVersion": "personal-web-sticker-request-v1",
        "contractVersion": "personal-web-sticker-handoff-v1",
        "bridgeRunId": request.bridge_run_id,
        "client": {"name": "Personal_Web", "gitCommit": request.client_commit},
        "input": {
            "safeBasename": request.safe_basename,
            "mimeType": request.mime_type,
            "bytes": request.input_bytes,
            "sha256": request.input_sha256,
        },
        "options": {
            "mode": request.options.mode.value,
            "aiModel": request.options.ai_model,
            "alphaMatting": request.options.alpha_matting,
            "paddingPixels": request.options.padding_pixels,
            "alphaCropThreshold": request.options.alpha_crop_threshold,
        },
    }


def _emit_stdout(data: dict) -> None:
    print(compact_json(data))


def run_process_request(request_path: str) -> int:
    prune_bridge_runs()
    tool_run_id = new_run_id()
    run_dir = bridge_runs_root() / tool_run_id
    handoff_dir = run_dir / "handoff"
    events_path = run_dir / "events.jsonl"
    running_marker = run_dir / ".running"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    running_marker.write_text(str(time.time()), encoding="utf-8")
    events = BridgeEventWriter(events_path, bridge_run_id=None, tool_run_id=tool_run_id)
    request = None
    manifest_path = handoff_dir / "result.json"
    try:
        events.write("bridge.request.received")
        events.write("bridge.request.validation_started")
        request_data = load_request(request_path)
        request = validate_request(request_data)
        events.bridge_run_id = request.bridge_run_id
        events.write("bridge.request.validation_succeeded")
        events.write("bridge.input.hash_verified", bytes=request.input_bytes, mimeType=request.mime_type)
        write_json_atomic(run_dir / "sanitized-request.json", _sanitized_request(request))

        events.write("bridge.processing.started")
        loaded = load_image(request.input_path)
        with contextlib.redirect_stdout(io.StringIO()):
            result = process_image(
                loaded.image,
                original_mode=loaded.original_mode,
                detected_format=loaded.detected_format,
                options=request.options,
                input_path=request.input_path,
                bridge_metadata={
                    "external_correlation_id": request.bridge_run_id,
                    "bridge_contract_version": "personal-web-sticker-handoff-v1",
                    "bridge_client_name": "Personal_Web",
                    "bridge_client_commit": request.client_commit,
                },
            )
        events.write("bridge.processing.route_selected", selectedRoute=result.selected_mode.value)
        events.write("bridge.processing.quality_evaluated", verdict=result.final_quality_result)
        processed_path = export_png_to_path(result.output_image, handoff_dir / "processed.png", overwrite=True)
        events.write("bridge.handoff.output_written", output="processed.png")
        report_target = copy_report(result.report_path, handoff_dir / "report.json")
        if report_target:
            events.write("bridge.handoff.report_written", report="report.json")
        manifest = output_manifest(
            request=request,
            result=result,
            tool_run_id=tool_run_id,
            processed_path=processed_path,
            events_path=events_path,
            report_target=report_target,
        )
        write_json_atomic(manifest_path, manifest)
        events.write("bridge.handoff.manifest_written", manifest="result.json")
        events.write("bridge.processing.completed")
        out = response(
            ok=True,
            bridge_run_id=request.bridge_run_id,
            tool_run_id=tool_run_id,
            manifest_relative_path=relative_to_root(manifest_path),
        )
        events.write("bridge.response.emitted", ok=True)
        _emit_stdout(out)
        return 0
    except Exception as exc:
        code = getattr(exc, "code", "BRIDGE_INTERNAL_FAILURE")
        user_message = getattr(exc, "user_message", "处理失败，请查看本地日志。")
        bridge_run_id = request.bridge_run_id if request else None
        if isinstance(exc, BridgeContractError):
            events.write("bridge.request.validation_failed", errorCode=code)
        else:
            events.write("bridge.processing.failed", errorCode=code)
        report_target = None
        report_path = getattr(exc, "report_path", None)
        if report_path:
            report_target = copy_report(Path(report_path), handoff_dir / "report.json")
        manifest = failure_manifest(
            bridge_run_id=bridge_run_id,
            tool_run_id=tool_run_id,
            events_path=events_path,
            error_code=code,
            user_message=user_message,
            request=request,
            report_target=report_target,
        )
        write_json_atomic(manifest_path, manifest)
        events.write("bridge.handoff.manifest_written", manifest="result.json")
        events.write("bridge.response.emitted", ok=False, errorCode=code)
        _emit_stdout(
            response(
                ok=False,
                bridge_run_id=bridge_run_id,
                tool_run_id=tool_run_id,
                manifest_relative_path=relative_to_root(manifest_path),
                error_code=code,
            )
        )
        return exit_code_for_error(exc)
    finally:
        if running_marker.exists():
            running_marker.unlink()
