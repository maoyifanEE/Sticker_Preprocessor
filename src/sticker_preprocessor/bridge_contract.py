from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .image_io import MAX_DIMENSION, MAX_FILE_SIZE, MAX_PIXELS
from .models import ProcessingMode, ProcessingOptions, StickerPreprocessorError
from .runtime_paths import project_root

CONTRACT_VERSION = "personal-web-sticker-handoff-v1"
CAPABILITIES_SCHEMA_VERSION = "sticker-preprocessor-capabilities-v1"
REQUEST_SCHEMA_VERSION = "personal-web-sticker-request-v1"
RESULT_SCHEMA_VERSION = "sticker-preprocessor-result-v1"
RESPONSE_SCHEMA_VERSION = "sticker-preprocessor-bridge-response-v1"
SUPPORTED_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")
SUPPORTED_MODELS = ("silueta", "u2netp", "isnet-general-use")
BRIDGE_RUN_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BridgeContractError(StickerPreprocessorError):
    code = "BRIDGE_INVALID_REQUEST"
    user_message = "请求格式无效，无法处理图片。"


class UnsupportedContractError(BridgeContractError):
    code = "BRIDGE_UNSUPPORTED_CONTRACT"
    user_message = "联动协议版本不受支持。"


@dataclass(frozen=True)
class ValidatedBridgeRequest:
    raw: dict[str, Any]
    bridge_run_id: str
    input_path: Path
    safe_basename: str
    mime_type: str
    input_bytes: int
    input_sha256: str
    options: ProcessingOptions
    client_commit: str | None


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root(),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def tool_info() -> dict[str, str | None]:
    return {
        "name": "Sticker_Preprocessor",
        "version": __version__,
        "gitCommit": git_commit(),
        "pythonVersion": platform.python_version(),
    }


def capabilities() -> dict[str, Any]:
    return {
        "schemaVersion": CAPABILITIES_SCHEMA_VERSION,
        "contractVersions": [CONTRACT_VERSION],
        "tool": tool_info(),
        "supportedInputMimeTypes": list(SUPPORTED_MIME_TYPES),
        "supportedModes": [mode.value for mode in ProcessingMode],
        "supportedModels": list(SUPPORTED_MODELS),
        "defaults": {
            "mode": ProcessingMode.AUTO.value,
            "aiModel": "silueta",
            "alphaMatting": False,
            "paddingPixels": 8,
            "alphaCropThreshold": 8,
        },
        "limits": {
            "maxInputBytes": MAX_FILE_SIZE,
            "maxDimension": MAX_DIMENSION,
            "maxPixels": MAX_PIXELS,
        },
        "reportSchemaVersion": "1.0",
        "resultSchemaVersion": RESULT_SCHEMA_VERSION,
    }


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def load_request(path: str | Path) -> dict[str, Any]:
    request_path = Path(path)
    if not request_path.is_file():
        raise BridgeContractError("request_json_missing")
    try:
        data = json.loads(request_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BridgeContractError("request_json_invalid") from exc
    if not isinstance(data, dict):
        raise BridgeContractError("request_json_not_object")
    return data


def _require_exact_keys(data: dict[str, Any], keys: set[str], label: str) -> None:
    if set(data) != keys:
        raise BridgeContractError(f"{label}_keys_invalid")


def _validate_options(data: dict[str, Any]) -> ProcessingOptions:
    _require_exact_keys(
        data,
        {"mode", "aiModel", "alphaMatting", "paddingPixels", "alphaCropThreshold"},
        "options",
    )
    mode = data["mode"]
    ai_model = data["aiModel"]
    if mode not in {item.value for item in ProcessingMode}:
        raise BridgeContractError("mode_unsupported")
    if ai_model not in SUPPORTED_MODELS:
        raise BridgeContractError("model_unsupported")
    if not isinstance(data["alphaMatting"], bool):
        raise BridgeContractError("alpha_matting_invalid")
    padding = data["paddingPixels"]
    crop = data["alphaCropThreshold"]
    if not isinstance(padding, int) or padding < 0 or padding > 128:
        raise BridgeContractError("padding_invalid")
    if not isinstance(crop, int) or crop < 0 or crop > 255:
        raise BridgeContractError("crop_threshold_invalid")
    return ProcessingOptions(
        mode=ProcessingMode(mode),
        ai_model=ai_model,
        alpha_matting=data["alphaMatting"],
        padding_pixels=padding,
        alpha_crop_threshold=crop,
    )


def validate_request(data: dict[str, Any]) -> ValidatedBridgeRequest:
    _require_exact_keys(
        data,
        {"schemaVersion", "contractVersion", "bridgeRunId", "createdAt", "client", "input", "options"},
        "request",
    )
    if data["schemaVersion"] != REQUEST_SCHEMA_VERSION:
        raise BridgeContractError("request_schema_unsupported")
    if data["contractVersion"] != CONTRACT_VERSION:
        raise UnsupportedContractError()
    bridge_run_id = data["bridgeRunId"]
    if not isinstance(bridge_run_id, str) or not BRIDGE_RUN_RE.fullmatch(bridge_run_id):
        raise BridgeContractError("bridge_run_id_invalid")
    client = data["client"]
    if not isinstance(client, dict):
        raise BridgeContractError("client_invalid")
    _require_exact_keys(client, {"name", "gitCommit"}, "client")
    if client["name"] != "Personal_Web":
        raise BridgeContractError("client_name_invalid")
    input_data = data["input"]
    if not isinstance(input_data, dict):
        raise BridgeContractError("input_invalid")
    _require_exact_keys(input_data, {"path", "safeBasename", "mimeType", "bytes", "sha256"}, "input")
    if input_data["mimeType"] not in SUPPORTED_MIME_TYPES:
        raise BridgeContractError("mime_type_unsupported")
    if Path(str(input_data["safeBasename"])).name != input_data["safeBasename"]:
        raise BridgeContractError("safe_basename_invalid")
    claimed_bytes = input_data["bytes"]
    claimed_hash = input_data["sha256"]
    if not isinstance(claimed_bytes, int) or claimed_bytes <= 0:
        raise BridgeContractError("input_bytes_invalid")
    if not isinstance(claimed_hash, str) or not SHA256_RE.fullmatch(claimed_hash):
        raise BridgeContractError("input_hash_invalid")
    input_path = Path(str(input_data["path"]))
    if not input_path.is_absolute() or not input_path.is_file():
        raise BridgeContractError("input_path_invalid")
    stat = input_path.stat()
    if stat.st_size != claimed_bytes:
        raise BridgeContractError("input_bytes_mismatch")
    actual_hash = sha256_path(input_path)
    if actual_hash != claimed_hash:
        raise BridgeContractError("input_hash_mismatch")
    options = _validate_options(data["options"])
    return ValidatedBridgeRequest(
        raw=data,
        bridge_run_id=bridge_run_id,
        input_path=input_path,
        safe_basename=input_data["safeBasename"],
        mime_type=input_data["mimeType"],
        input_bytes=claimed_bytes,
        input_sha256=claimed_hash,
        options=options,
        client_commit=client["gitCommit"] if isinstance(client["gitCommit"], str) else None,
    )


def exit_code_for_error(exc: Exception) -> int:
    code = getattr(exc, "code", "")
    if code == UnsupportedContractError.code:
        return 6
    if code == "AI_COMPONENT_UNAVAILABLE":
        return 3
    if isinstance(exc, BridgeContractError):
        return 2
    if isinstance(exc, StickerPreprocessorError):
        return 4
    return 5


def response(
    *,
    ok: bool,
    bridge_run_id: str | None,
    tool_run_id: str | None,
    manifest_relative_path: str | None,
    error_code: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schemaVersion": RESPONSE_SCHEMA_VERSION,
        "contractVersion": CONTRACT_VERSION,
        "ok": ok,
        "bridgeRunId": bridge_run_id,
        "toolRunId": tool_run_id,
        "resultManifestRelativePath": manifest_relative_path,
    }
    if error_code:
        data["errorCode"] = error_code
    return data


def stderr_line(message: str) -> None:
    print(message, file=sys.stderr)
