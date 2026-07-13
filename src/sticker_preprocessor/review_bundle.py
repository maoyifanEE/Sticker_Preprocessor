from __future__ import annotations

import json
import logging
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import __version__
from .diagnostics import git_commit, sha256_file
from .models import PreviewBackground, ProcessingOptions, ProcessingResult
from .preview import make_preview
from .runtime_paths import logs_dir, project_root, review_bundles_dir

LOGGER = logging.getLogger(__name__)
PRIVACY_WARNING = "诊断包包含本次输入和输出图片，仅在你确认后手动分享。"


@dataclass(frozen=True)
class ReviewBundleResult:
    path: Path
    privacy_warning: str = PRIVACY_WARNING


def _short_commit() -> str:
    commit = git_commit()
    return (commit or "nogit")[:8]


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _zip_write_text(zf: zipfile.ZipFile, name: str, text: str) -> None:
    zf.writestr(name, text.encode("utf-8"))


def _save_preview_to_zip(zf: zipfile.ZipFile, name: str, image: Image.Image, background: PreviewBackground) -> None:
    from io import BytesIO

    buffer = BytesIO()
    make_preview(image, background, (640, 640)).save(buffer, format="PNG")
    zf.writestr(name, buffer.getvalue())


def _relevant_log(run_id: str) -> str:
    log_path = logs_dir() / "sticker_preprocessor.log"
    if not log_path.exists():
        return ""
    lines = []
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if run_id in line:
            lines.append(line)
    return "\n".join(lines)


def create_review_bundle(
    *,
    input_path: str | Path,
    report_path: str | Path,
    run_id: str,
    source_image: Image.Image,
    result: ProcessingResult | None,
    options: ProcessingOptions,
) -> ReviewBundleResult:
    root = project_root()
    out_dir = review_bundles_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / f"sticker-review-{_timestamp()}-{_short_commit()}-{run_id}.zip"
    input_path = Path(input_path)
    report_path = Path(report_path)
    included: list[str] = []
    output_sha = None
    output_dimensions = None
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(report_path, "report.json")
        included.append("report.json")
        zf.write(input_path, f"input/{input_path.name}")
        included.append(f"input/{input_path.name}")
        if result is not None:
            from io import BytesIO

            buffer = BytesIO()
            result.output_image.save(buffer, format="PNG")
            payload = buffer.getvalue()
            zf.writestr("output/processed.png", payload)
            included.append("output/processed.png")
            import hashlib

            output_sha = hashlib.sha256(payload).hexdigest()
            output_dimensions = result.output_size
        backgrounds = {
            "light": PreviewBackground.LIGHT,
            "dark": PreviewBackground.DARK,
            "web": PreviewBackground.WEB,
        }
        for label, background in backgrounds.items():
            name = f"previews/source-{label}.png"
            _save_preview_to_zip(zf, name, source_image, background)
            included.append(name)
            if result is not None:
                name = f"previews/output-{label}.png"
                _save_preview_to_zip(zf, name, result.output_image, background)
                included.append(name)
        log_text = _relevant_log(run_id)
        _zip_write_text(zf, "logs/relevant-log.txt", log_text)
        included.append("logs/relevant-log.txt")
        manifest = {
            "schema_version": "1.0",
            "run_id": run_id,
            "application_version": __version__,
            "git_commit": git_commit(),
            "python_version": sys.version.split()[0],
            "safe_input_basename": input_path.name,
            "input_sha256": sha256_file(input_path),
            "input_file_size": input_path.stat().st_size,
            "output_sha256": output_sha,
            "output_dimensions": output_dimensions,
            "requested_route": options.mode.value,
            "selected_route": result.selected_mode.value if result else None,
            "model": options.ai_model,
            "options": asdict(options),
            "quality_verdict": result.final_quality_result if result else "FAIL",
            "included_files": included,
        }
        _zip_write_text(zf, "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    LOGGER.info("review_bundle.created run_id=%s bundle=%s", run_id, bundle_path.name)
    return ReviewBundleResult(bundle_path.relative_to(root))


def create_qa_zip(run_dir: Path, *, timestamp: str, short_commit: str) -> Path:
    out_dir = review_bundles_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"sticker-qa-{timestamp}-{short_commit}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(run_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(run_dir).as_posix())
    LOGGER.info("review_bundle.created run_id=batch bundle=%s", zip_path.name)
    return zip_path.relative_to(project_root())
