from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_root() -> Path:
    override = os.environ.get("STICKER_PREPROCESSOR_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return project_root() / ".runtime"


def logs_dir() -> Path:
    return runtime_root() / "logs"


def rembg_models_dir() -> Path:
    return runtime_root() / "models" / "rembg"


def temp_dir() -> Path:
    return runtime_root() / "temp"


def test_temp_dir() -> Path:
    return runtime_root() / "test-temp"


def reports_dir() -> Path:
    return runtime_root() / "reports"


def qa_runs_dir() -> Path:
    return runtime_root() / "qa-runs"


def review_bundles_dir() -> Path:
    return runtime_root() / "review-bundles"


def output_dir() -> Path:
    return project_root() / "output"


def input_dir() -> Path:
    return project_root() / "input"


def ensure_runtime_dirs() -> None:
    for path in (
        logs_dir(),
        rembg_models_dir(),
        temp_dir(),
        test_temp_dir(),
        reports_dir(),
        qa_runs_dir(),
        review_bundles_dir(),
        output_dir(),
        input_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def configure_process_temp() -> Path:
    temp = temp_dir()
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(temp)
    os.environ["TEMP"] = str(temp)
    os.environ["TMPDIR"] = str(temp)
    return temp


def configure_u2net_home() -> Path:
    models = rembg_models_dir()
    models.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("U2NET_HOME", str(models))
    return Path(os.environ["U2NET_HOME"])
