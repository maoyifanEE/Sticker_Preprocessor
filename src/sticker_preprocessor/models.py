from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from PIL import Image


class ProcessingMode(StrEnum):
    AUTO = "auto"
    ALPHA_CLEANUP = "alpha_cleanup"
    CHECKERBOARD = "checkerboard"
    AI = "ai"


class PreviewBackground(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    WEB = "web"


class OperationType(StrEnum):
    LOAD = "load"
    PROCESS = "process"
    EXPORT = "export"


class StickerPreprocessorError(Exception):
    code = "STICKER_PREPROCESSOR_ERROR"
    user_message = "处理失败。"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        super().__init__(message or self.user_message)
        if code:
            self.code = code


class InvalidImageError(StickerPreprocessorError):
    code = "INVALID_IMAGE"
    user_message = "图片文件已损坏或无法解码。"


class UnsupportedFormatError(InvalidImageError):
    code = "UNSUPPORTED_FORMAT"
    user_message = "不支持此图片格式。"


class AnimatedImageError(InvalidImageError):
    code = "ANIMATED_IMAGE"
    user_message = "暂不支持动态图。"


class ImageTooLargeError(InvalidImageError):
    code = "IMAGE_TOO_LARGE"
    user_message = "图片尺寸过大。"


class EmptyForegroundError(StickerPreprocessorError):
    code = "EMPTY_FOREGROUND"
    user_message = "没有检测到可保留的前景。"


class CheckerboardNotDetectedError(StickerPreprocessorError):
    code = "CHECKERBOARD_NOT_DETECTED"
    user_message = "未能可靠识别内嵌棋盘格，请改用 AI 去背景。"


class AIComponentUnavailableError(StickerPreprocessorError):
    code = "AI_COMPONENT_UNAVAILABLE"
    user_message = "AI 组件未安装，请重新运行安装脚本或使用非 AI 模式。"


class AIModelError(StickerPreprocessorError):
    code = "AI_MODEL_ERROR"
    user_message = "AI 模型处理失败，请查看本地日志。"


class InvalidOutputError(StickerPreprocessorError):
    code = "INVALID_OUTPUT"
    user_message = "输出结果不是有效的透明 RGBA PNG。"


class ExportError(StickerPreprocessorError):
    code = "EXPORT_ERROR"
    user_message = "导出失败。"


@dataclass(frozen=True)
class ImageAnalysis:
    original_mode: str
    detected_format: str
    width: int
    height: int
    total_pixels: int
    has_source_alpha_channel: bool
    alpha_min: int
    alpha_max: int
    fully_transparent_count: int
    semitransparent_count: int
    nonopaque_count: int
    transparent_fraction: float
    meaningful_transparency: bool
    alpha_bbox: tuple[int, int, int, int] | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckerboardAnalysis:
    detected: bool
    confidence: float
    first_color: tuple[int, int, int] | None
    second_color: tuple[int, int, int] | None
    estimated_tile_size: int | None
    phase: tuple[int, int] | None
    border_coverage: float
    pattern_accuracy: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessingOptions:
    mode: ProcessingMode = ProcessingMode.AUTO
    padding_pixels: int = 8
    alpha_crop_threshold: int = 8
    ai_model: str = "silueta"
    alpha_matting: bool = False


@dataclass(frozen=True)
class ProcessingResult:
    output_image: Image.Image
    selected_mode: ProcessingMode
    source_analysis: ImageAnalysis
    checkerboard_analysis: CheckerboardAnalysis | None
    original_size: tuple[int, int]
    output_size: tuple[int, int]
    transparent_fraction: float
    processing_duration: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LoadedImage:
    path: Path
    image: Image.Image
    detected_format: str
    original_mode: str
