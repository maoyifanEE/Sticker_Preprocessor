from __future__ import annotations

import types

import pytest
from PIL import Image

import sticker_preprocessor.rembg_adapter as adapter
from sticker_preprocessor.models import AIComponentUnavailableError, AIModelError


def test_missing_rembg_produces_clear_typed_error(monkeypatch):
    monkeypatch.setattr(adapter.importlib.util, "find_spec", lambda name: None)

    def fake_import(_name):
        raise ModuleNotFoundError("rembg")

    monkeypatch.setattr(adapter.importlib, "import_module", fake_import)
    adapter._SESSIONS.clear()
    with pytest.raises(AIComponentUnavailableError):
        adapter.get_session("silueta")


def test_model_names_are_allowlisted():
    assert adapter.validate_model_name("silueta") == "silueta"


def test_arbitrary_model_path_name_rejected():
    with pytest.raises(AIModelError):
        adapter.validate_model_name("../model.onnx")


def test_session_is_cached(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(new_session=lambda model: calls.append(model) or object())
    monkeypatch.setattr(adapter.importlib, "import_module", lambda name: fake)
    adapter._SESSIONS.clear()
    first = adapter.get_session("u2netp")
    second = adapter.get_session("u2netp")
    assert first is second
    assert calls == ["u2netp"]


def test_repeated_operations_reuse_one_session(monkeypatch):
    calls = []

    def new_session(model):
        calls.append(model)
        return object()

    def remove(image, **_kwargs):
        return image.convert("RGBA")

    fake = types.SimpleNamespace(new_session=new_session, remove=remove)
    monkeypatch.setattr(adapter.importlib, "import_module", lambda name: fake)
    adapter._SESSIONS.clear()
    adapter.remove_background(Image.new("RGB", (4, 4), "white"), model_name="silueta")
    adapter.remove_background(Image.new("RGB", (4, 4), "white"), model_name="silueta")
    assert calls == ["silueta"]


def test_u2net_home_is_configured_before_lazy_import(monkeypatch):
    order = []

    def fake_configure():
        order.append("configure")

    def fake_import(_name):
        order.append("import")
        return types.SimpleNamespace(new_session=lambda model: object())

    monkeypatch.setattr(adapter, "configure_u2net_home", fake_configure)
    monkeypatch.setattr(adapter.importlib, "import_module", fake_import)
    adapter._SESSIONS.clear()
    adapter.get_session("isnet-general-use")
    assert order == ["configure", "import"]


def test_rembg_exception_is_wrapped_safely(monkeypatch):
    raw_message = "C:\\Users\\someone\\secret\\model.onnx https://example.invalid/internal traceback"
    fake = types.SimpleNamespace(
        new_session=lambda model: object(),
        remove=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(raw_message)),
    )
    monkeypatch.setattr(adapter.importlib, "import_module", lambda name: fake)
    adapter._SESSIONS.clear()
    with pytest.raises(AIModelError) as exc_info:
        adapter.remove_background(Image.new("RGB", (4, 4), "white"))
    assert raw_message not in str(exc_info.value)
    assert str(exc_info.value) == AIModelError.user_message


def test_model_initialization_error_does_not_expose_raw_text(monkeypatch):
    raw_message = "download https://example.invalid/model.onnx into C:\\Users\\name"
    fake = types.SimpleNamespace(new_session=lambda model: (_ for _ in ()).throw(RuntimeError(raw_message)))
    monkeypatch.setattr(adapter.importlib, "import_module", lambda name: fake)
    adapter._SESSIONS.clear()
    with pytest.raises(AIModelError) as exc_info:
        adapter.get_session("silueta")
    assert raw_message not in str(exc_info.value)
    assert str(exc_info.value) == AIModelError.user_message


def test_mocked_valid_rgba_result_is_returned(monkeypatch):
    fake = types.SimpleNamespace(
        new_session=lambda model: object(),
        remove=lambda image, **_kwargs: Image.new("RGBA", image.size, (0, 0, 0, 0)),
    )
    monkeypatch.setattr(adapter.importlib, "import_module", lambda name: fake)
    adapter._SESSIONS.clear()
    out = adapter.remove_background(Image.new("RGB", (4, 4), "white"))
    assert out.mode == "RGBA"
    assert out.size == (4, 4)
