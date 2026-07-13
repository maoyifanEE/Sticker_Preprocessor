from __future__ import annotations

import json
import zipfile

import pytest
from PIL import Image, ImageDraw

from sticker_preprocessor.models import ProcessingMode, ProcessingOptions
from sticker_preprocessor.pipeline import process_image
from sticker_preprocessor.qa_batch import run_qa_batch
from sticker_preprocessor.review_bundle import create_review_bundle


def transparent_subject() -> Image.Image:
    img = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((6, 6, 17, 17), fill=(200, 0, 0, 255))
    return img


def test_report_created_on_success(tmp_path):
    input_path = tmp_path / "source.png"
    transparent_subject().save(input_path)
    result = process_image(
        transparent_subject(),
        original_mode="RGBA",
        detected_format="PNG",
        input_path=input_path,
    )
    assert result.report_path is not None
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["run_id"] == result.run_id
    assert report["safe_input_basename"] == "source.png"
    assert str(tmp_path) not in json.dumps(report)
    assert "source" in report["stage_diagnostics"]
    assert "final_export_candidate" in report["stage_diagnostics"]


def test_report_created_on_controlled_failure(tmp_path):
    input_path = tmp_path / "opaque.png"
    Image.new("RGBA", (20, 20), (255, 255, 255, 255)).save(input_path)
    with pytest.raises(Exception) as exc_info:
        process_image(
            Image.new("RGBA", (20, 20), (255, 255, 255, 255)),
            original_mode="RGBA",
            detected_format="PNG",
            options=ProcessingOptions(mode=ProcessingMode.ALPHA_CLEANUP),
            input_path=input_path,
        )
    report_path = getattr(exc_info.value, "report_path", None)
    assert report_path is not None
    assert report_path.exists()


def test_input_sha256_in_report_is_correct(tmp_path):
    input_path = tmp_path / "source.png"
    transparent_subject().save(input_path)
    result = process_image(transparent_subject(), original_mode="RGBA", detected_format="PNG", input_path=input_path)
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    import hashlib

    assert report["input_sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()


def test_review_bundle_contains_manifest_report_images_and_previews(tmp_path):
    input_path = tmp_path / "source.png"
    image = transparent_subject()
    image.save(input_path)
    options = ProcessingOptions(mode=ProcessingMode.ALPHA_CLEANUP)
    result = process_image(image, original_mode="RGBA", detected_format="PNG", options=options, input_path=input_path)
    bundle = create_review_bundle(
        input_path=input_path,
        report_path=result.report_path,
        run_id=result.run_id,
        source_image=image,
        result=result,
        options=options,
    )
    from sticker_preprocessor.runtime_paths import project_root

    bundle_path = project_root() / bundle.path
    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "report.json" in names
        assert "logs/relevant-log.txt" in names
        assert "input/source.png" in names
        assert "output/processed.png" in names
        assert "previews/source-light.png" in names
        assert "previews/source-dark.png" in names
        assert "previews/source-web.png" in names
        assert "previews/output-light.png" in names
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["safe_input_basename"] == "source.png"


def test_qa_batch_processes_multiple_files_and_continues_after_failure(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    good = input_dir / "good.png"
    bad = input_dir / "bad.png"
    original_bytes = b"not an image"
    transparent_subject().save(good)
    bad.write_bytes(original_bytes)
    passed, failed, bundle = run_qa_batch(input_dir, mode=ProcessingMode.ALPHA_CLEANUP)
    assert passed == 1
    assert failed == 1
    assert bad.read_bytes() == original_bytes
    from sticker_preprocessor.runtime_paths import project_root

    assert (project_root() / bundle).exists()
