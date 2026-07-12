from __future__ import annotations

import importlib


def test_all_modules_import_without_starting_ui():
    modules = [
        "sticker_preprocessor.models",
        "sticker_preprocessor.image_io",
        "sticker_preprocessor.analyzer",
        "sticker_preprocessor.alpha_tools",
        "sticker_preprocessor.checkerboard",
        "sticker_preprocessor.rembg_adapter",
        "sticker_preprocessor.pipeline",
        "sticker_preprocessor.preview",
        "sticker_preprocessor.exporter",
        "sticker_preprocessor.runtime_paths",
        "sticker_preprocessor.logging_config",
    ]
    for name in modules:
        assert importlib.import_module(name)


def test_self_check_exits_successfully_without_model_download():
    from sticker_preprocessor.__main__ import self_check

    assert self_check() == 0


def test_ui_module_import_does_not_process_files():
    module = importlib.import_module("sticker_preprocessor.ui.main_window")
    assert hasattr(module, "MainWindow")


def test_main_version_output(capsys):
    from sticker_preprocessor.__main__ import main

    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out


def test_runtime_paths_are_inside_project():
    from sticker_preprocessor.runtime_paths import output_dir, runtime_root

    root = runtime_root()
    assert root.name == ".runtime"
    assert output_dir().name == "output"
