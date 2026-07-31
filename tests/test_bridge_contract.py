from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from sticker_preprocessor.bridge_contract import capabilities, compact_json, sha256_path
from sticker_preprocessor.runtime_paths import project_root


def make_source(path: Path) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 23, 23), fill=(20, 120, 220, 255))
    image.save(path)


def make_request(path: Path, *, bridge_run_id: str = "a" * 32) -> dict:
    payload = path.read_bytes()
    return {
        "schemaVersion": "personal-web-sticker-request-v1",
        "contractVersion": "personal-web-sticker-handoff-v1",
        "bridgeRunId": bridge_run_id,
        "createdAt": "2026-07-31T00:00:00Z",
        "client": {"name": "Personal_Web", "gitCommit": "b" * 40},
        "input": {
            "path": str(path.resolve()),
            "safeBasename": path.name,
            "mimeType": "image/png",
            "bytes": len(payload),
            "sha256": sha256_path(path),
        },
        "options": {
            "mode": "alpha_cleanup",
            "aiModel": "silueta",
            "alphaMatting": False,
            "paddingPixels": 8,
            "alphaCropThreshold": 8,
        },
    }


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sticker_preprocessor", *args],
        cwd=project_root(),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_capabilities_is_single_json_object() -> None:
    result = run_cli("--bridge-capabilities")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.count("\n") == 1
    data = json.loads(result.stdout)
    assert data == capabilities()
    assert data["schemaVersion"] == "sticker-preprocessor-capabilities-v1"
    assert "personal-web-sticker-handoff-v1" in data["contractVersions"]
    assert "silueta" in data["supportedModels"]
    assert compact_json(data).startswith("{")


def test_bridge_success_writes_manifest_events_and_relative_paths(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_source(source)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(make_request(source)), encoding="utf-8")

    result = run_cli("--bridge-process-request", str(request_path))

    assert result.returncode == 0
    assert result.stdout.count("\n") == 1
    response = json.loads(result.stdout)
    assert response["ok"] is True
    assert response["bridgeRunId"] == "a" * 32
    manifest_path = project_root() / response["resultManifestRelativePath"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["toolRunId"] == response["toolRunId"]
    assert not Path(manifest["output"]["relativePath"]).is_absolute()
    output_path = project_root() / manifest["output"]["relativePath"]
    assert output_path.is_file()
    assert sha256_path(output_path) == manifest["output"]["sha256"]
    assert manifest["output"]["alpha"]["fullyTransparentCount"] > 0
    events_path = project_root() / manifest["artifacts"]["eventsRelativePath"]
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert {event["event"] for event in events} >= {
        "bridge.request.validation_succeeded",
        "bridge.processing.started",
        "bridge.handoff.manifest_written",
        "bridge.response.emitted",
    }
    report = json.loads((project_root() / manifest["artifacts"]["reportRelativePath"]).read_text(encoding="utf-8"))
    assert report["external_correlation_id"] == "a" * 32
    assert report["bridge_contract_version"] == "personal-web-sticker-handoff-v1"


def test_bridge_rejects_hash_mismatch_and_writes_failure_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_source(source)
    request = make_request(source)
    request["input"]["sha256"] = "0" * 64
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    result = run_cli("--bridge-process-request", str(request_path))

    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response["ok"] is False
    manifest = json.loads((project_root() / response["resultManifestRelativePath"]).read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["failure"]["code"] == "BRIDGE_INVALID_REQUEST"


def test_bridge_rejects_unknown_request_fields(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_source(source)
    request = make_request(source)
    request["outputPath"] = str(tmp_path / "bad.png")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    result = run_cli("--bridge-process-request", str(request_path))

    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response["ok"] is False
