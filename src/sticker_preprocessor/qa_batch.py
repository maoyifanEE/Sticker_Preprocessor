from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .diagnostics import git_commit, sha256_file
from .exporter import export_png_to_path
from .image_io import SUPPORTED_FORMATS, load_image
from .models import ProcessingMode, ProcessingOptions, StickerPreprocessorError
from .pipeline import process_image
from .preview import make_preview
from .review_bundle import create_qa_zip
from .runtime_paths import project_root, qa_runs_dir

LOGGER = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _short_commit() -> str:
    return (git_commit() or "nogit")[:8]


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}


def run_qa_batch(
    input_directory: str | Path,
    *,
    mode: ProcessingMode = ProcessingMode.AUTO,
    model: str = "silueta",
    alpha_matting: bool = False,
    padding: int = 8,
    crop_threshold: int = 8,
) -> tuple[int, int, Path]:
    source_dir = Path(input_directory)
    timestamp = _timestamp()
    short_commit = _short_commit()
    run_dir = qa_runs_dir() / f"{timestamp}-{short_commit}"
    output_dir = run_dir / "output"
    preview_dir = run_dir / "previews"
    report_dir = run_dir / "reports"
    input_copy_dir = run_dir / "input"
    for path in (output_dir, preview_dir, report_dir, input_copy_dir):
        path.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "schema_version": "1.0",
        "timestamp": timestamp,
        "git_commit": git_commit(),
        "input_directory": source_dir.name,
        "items": [],
    }
    pass_count = 0
    fail_count = 0
    options = ProcessingOptions(
        mode=mode,
        padding_pixels=padding,
        alpha_crop_threshold=crop_threshold,
        ai_model=model,
        alpha_matting=alpha_matting,
    )
    files = sorted(path for path in source_dir.iterdir() if path.is_file() and _is_supported(path))
    for path in files:
        item = {
            "input": path.name,
            "input_sha256": sha256_file(path),
            "status": "FAIL",
            "report": None,
            "output": None,
            "error": None,
        }
        try:
            loaded = load_image(path)
            if loaded.detected_format not in SUPPORTED_FORMATS:
                raise ValueError("unsupported decoded format")
            shutil.copy2(path, input_copy_dir / path.name)
            result = process_image(
                loaded.image,
                original_mode=loaded.original_mode,
                detected_format=loaded.detected_format,
                options=options,
                input_path=path,
            )
            output_path = export_png_to_path(result.output_image, output_dir / f"{path.stem}_sticker.png", overwrite=True)
            if result.report_path is not None:
                report_source = project_root() / result.report_path
                report_target = report_dir / report_source.name
                shutil.copy2(report_source, report_target)
                item["report"] = report_target.relative_to(run_dir).as_posix()
            item["output"] = output_path.relative_to(run_dir).as_posix()
            item["status"] = "PASS"
            item["run_id"] = result.run_id
            for label, background in (
                ("light", "light"),
                ("dark", "dark"),
                ("web", "web"),
            ):
                from .models import PreviewBackground

                bg = PreviewBackground(background)
                make_preview(loaded.image, bg, (640, 640)).save(preview_dir / f"{path.stem}-source-{label}.png")
                make_preview(result.output_image, bg, (640, 640)).save(preview_dir / f"{path.stem}-output-{label}.png")
            pass_count += 1
        except Exception as exc:
            fail_count += 1
            item["error"] = getattr(exc, "code", type(exc).__name__)
            report_path = getattr(exc, "report_path", None)
            if report_path is not None:
                report_source = Path(report_path)
                if not report_source.is_absolute():
                    report_source = project_root() / report_source
                if report_source.exists():
                    report_target = report_dir / report_source.name
                    shutil.copy2(report_source, report_target)
                    item["report"] = report_target.relative_to(run_dir).as_posix()
            if isinstance(exc, StickerPreprocessorError):
                LOGGER.info("run.failed input=%s code=%s", path.name, exc.code)
            else:
                LOGGER.exception("run.failed input=%s error=unexpected", path.name)
        manifest["items"].append(item)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_path = create_qa_zip(run_dir, timestamp=timestamp, short_commit=short_commit)
    return pass_count, fail_count, zip_path
