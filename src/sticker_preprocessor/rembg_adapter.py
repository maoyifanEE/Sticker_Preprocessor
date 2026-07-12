from __future__ import annotations

import importlib
import logging
import threading

from PIL import Image

from .models import AIComponentUnavailableError, AIModelError
from .runtime_paths import configure_u2net_home

LOGGER = logging.getLogger(__name__)

ALLOWED_MODELS = {"silueta", "u2netp", "isnet-general-use"}
DEFAULT_MODEL = "silueta"
_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, object] = {}


def validate_model_name(model_name: str) -> str:
    if model_name not in ALLOWED_MODELS:
        raise AIModelError("不支持的 AI 模型。")
    return model_name


def is_rembg_available() -> bool:
    return importlib.util.find_spec("rembg") is not None


def get_session(model_name: str = DEFAULT_MODEL) -> object:
    model = validate_model_name(model_name)
    with _SESSION_LOCK:
        if model in _SESSIONS:
            return _SESSIONS[model]
        configure_u2net_home()
        LOGGER.info("model_initialization_started model=%s", model)
        try:
            rembg = importlib.import_module("rembg")
        except ModuleNotFoundError as exc:
            LOGGER.info("model_initialization_failed model=%s reason=missing_rembg", model)
            raise AIComponentUnavailableError() from exc
        try:
            session = rembg.new_session(model)
        except Exception as exc:
            LOGGER.exception("model_initialization_failed model=%s", model)
            raise AIModelError(str(exc)) from exc
        _SESSIONS[model] = session
        LOGGER.info("model_initialization_succeeded model=%s", model)
        return session


def remove_background(
    image: Image.Image,
    *,
    model_name: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
) -> Image.Image:
    session = get_session(model_name)
    try:
        rembg = importlib.import_module("rembg")
        kwargs = {
            "session": session,
            "post_process_mask": False,
            "alpha_matting": alpha_matting,
        }
        if alpha_matting:
            kwargs.update(
                {
                    "alpha_matting_foreground_threshold": 240,
                    "alpha_matting_background_threshold": 10,
                    "alpha_matting_erode_size": 10,
                }
            )
        result = rembg.remove(image.convert("RGB"), **kwargs)
        rgba = result.convert("RGBA")
    except AIComponentUnavailableError:
        raise
    except Exception as exc:
        LOGGER.exception("processing_failed route=ai model=%s", model_name)
        raise AIModelError(str(exc)) from exc
    LOGGER.info("processing_succeeded route=ai model=%s output=%sx%s", model_name, rgba.width, rgba.height)
    return rgba
