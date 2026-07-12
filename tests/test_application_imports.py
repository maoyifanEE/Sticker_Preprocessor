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


def test_ui_static_controls_and_default_background():
    from sticker_preprocessor.models import OperationType
    from sticker_preprocessor.ui.main_window import BG_LABELS, DEFAULT_BACKGROUND_LABEL, MainWindow

    root = MainWindow()
    try:
        assert root.title() == "贴纸透明背景处理器"
        assert hasattr(root, "reset_btn")
        assert hasattr(root, "progress")
        assert hasattr(root, "save_as_btn")
        assert hasattr(root, "open_output_btn")
        assert DEFAULT_BACKGROUND_LABEL == "网页背景"
        assert "棋盘" not in DEFAULT_BACKGROUND_LABEL
        assert all("棋盘" not in label for label in BG_LABELS)
        assert str(root.process_btn["state"]) == "disabled"
        assert str(root.export_btn["state"]) == "disabled"
        root._set_controls_for_operation(OperationType.LOAD)
        assert str(root.open_btn["state"]) == "disabled"
        assert str(root.process_btn["state"]) == "disabled"
        assert str(root.export_btn["state"]) == "disabled"
        assert str(root.save_as_btn["state"]) == "disabled"
    finally:
        root.destroy()
