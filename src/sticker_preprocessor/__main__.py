from __future__ import annotations

import argparse
import logging
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

from . import __version__
from .logging_config import setup_logging
from .models import ProcessingMode, ProcessingOptions, StickerPreprocessorError
from .pipeline import process_image
from .qa_batch import run_qa_batch
from .rembg_adapter import is_rembg_available, validate_model_name
from .runtime_paths import configure_process_temp, ensure_runtime_dirs, output_dir, rembg_models_dir

LOGGER = logging.getLogger(__name__)


def self_check() -> int:
    checks: list[str] = []
    try:
        if not (sys.version_info >= (3, 11) and sys.version_info < (3, 14)):
            raise RuntimeError("Python version must be >=3.11,<3.14")
        checks.append(f"python={sys.version.split()[0]}")
        import tkinter  # noqa: F401

        checks.append("tkinter=ok")
        import PIL  # noqa: F401

        checks.append("pillow=ok")
        checks.append(f"numpy={np.__version__}")
        checks.append(f"rembg_installed={is_rembg_available()}")
        ensure_runtime_dirs()
        checks.append(f"temp_dir={configure_process_temp()}")
        checks.append(f"runtime_models={rembg_models_dir()}")
        checks.append(f"output_dir={output_dir()}")
    except Exception as exc:
        print("SELF_CHECK_FAIL")
        print(str(exc))
        return 1
    print("SELF_CHECK_PASS")
    for item in checks:
        print(item)
    return 0


def ui_smoke_test() -> int:
    from .ui.main_window import MainWindow

    root = MainWindow()
    root.update_idletasks()
    root.update()
    root.after(100, root.destroy)
    root.mainloop()
    print("UI_SMOKE_TEST_PASS")
    return 0


def ai_smoke_test(model: str) -> int:
    validate_model_name(model)
    configure_process_temp()
    with tempfile.TemporaryDirectory(prefix="sticker_ai_smoke_") as _tmp:
        img = Image.new("RGB", (96, 96), "white")
        draw = ImageDraw.Draw(img)
        draw.ellipse((24, 18, 74, 78), fill=(220, 30, 70))
        try:
            result = process_image(
                img,
                original_mode="RGB",
                detected_format="PNG",
                options=ProcessingOptions(mode=ProcessingMode.AI, ai_model=model),
            )
            alpha = np.asarray(result.output_image.getchannel("A"), dtype=np.uint8)
            if not np.any(alpha < 250):
                raise RuntimeError("AI result has no transparency")
        except Exception as exc:
            print("AI_SMOKE_TEST_FAIL")
            print(str(exc))
            return 1
    print("AI_SMOKE_TEST_PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(prog="sticker_preprocessor")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--ui-smoke-test", action="store_true")
    parser.add_argument("--ai-smoke-test", action="store_true")
    parser.add_argument("--model", default="silueta")
    parser.add_argument("--qa-batch")
    parser.add_argument("--qa-mode", default="auto")
    parser.add_argument("--qa-model", default="silueta")
    parser.add_argument("--qa-alpha-matting", action="store_true")
    parser.add_argument("--qa-padding", type=int, default=8)
    parser.add_argument("--qa-crop-threshold", type=int, default=8)
    parser.add_argument("--bridge-capabilities", action="store_true")
    parser.add_argument("--bridge-process-request")
    args = parser.parse_args(argv)
    if args.bridge_capabilities:
        from .bridge_cli import run_capabilities

        return run_capabilities()
    if args.bridge_process_request:
        from .bridge_cli import run_process_request

        return run_process_request(args.bridge_process_request)
    if args.version:
        print(__version__)
        return 0
    if args.self_check:
        return self_check()
    if args.ui_smoke_test:
        return ui_smoke_test()
    if args.ai_smoke_test:
        return ai_smoke_test(args.model)
    if args.qa_batch:
        try:
            passed, failed, bundle = run_qa_batch(
                args.qa_batch,
                mode=ProcessingMode(args.qa_mode),
                model=args.qa_model,
                alpha_matting=args.qa_alpha_matting,
                padding=args.qa_padding,
                crop_threshold=args.qa_crop_threshold,
            )
        except Exception as exc:
            print("QA_BATCH_PASS=0")
            print("QA_BATCH_FAIL=1")
            print(f"QA_ERROR={type(exc).__name__}")
            return 1
        print(f"QA_BATCH_PASS={passed}")
        print(f"QA_BATCH_FAIL={failed}")
        print(f"QA_REVIEW_BUNDLE={bundle}")
        return 0 if failed == 0 else 1
    try:
        from .app import run

        run()
        return 0
    except StickerPreprocessorError as exc:
        LOGGER.exception("application_failed")
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
