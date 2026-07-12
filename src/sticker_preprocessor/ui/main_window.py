from __future__ import annotations

import logging
import os
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from ..analyzer import analyze_image
from ..exporter import export_png, export_png_to_path, sanitize_filename
from ..image_io import load_image
from ..models import (
    ImageAnalysis,
    LoadedImage,
    OperationType,
    PreviewBackground,
    ProcessingMode,
    ProcessingOptions,
    ProcessingResult,
    StickerPreprocessorError,
)
from ..pipeline import process_image
from ..preview import make_preview
from ..rembg_adapter import DEFAULT_MODEL, has_cached_session
from ..runtime_paths import output_dir

LOGGER = logging.getLogger(__name__)

APP_TITLE = "贴纸透明背景处理器"
APP_SUBTITLE = "将图片处理为可直接用于网页的透明 PNG 贴纸"
FIRST_AI_MODEL_MESSAGE = "首次使用此模型时需要下载模型文件，请稍候。"
DEFAULT_BACKGROUND_LABEL = "网页背景"

MODE_LABELS = {
    "自动": ProcessingMode.AUTO,
    "清理真实透明": ProcessingMode.ALPHA_CLEANUP,
    "移除内嵌棋盘格": ProcessingMode.CHECKERBOARD,
    "AI 去背景": ProcessingMode.AI,
}
MODEL_LABELS = {
    "silueta：推荐，质量与体积平衡": "silueta",
    "u2netp：快速、轻量": "u2netp",
    "isnet-general-use：更精细、较慢": "isnet-general-use",
}
BG_LABELS = {
    "浅色": PreviewBackground.LIGHT,
    "深色": PreviewBackground.DARK,
    DEFAULT_BACKGROUND_LABEL: PreviewBackground.WEB,
}


@dataclass(frozen=True)
class LoadedPayload:
    loaded: LoadedImage
    analysis: ImageAnalysis
    preview_image: Image.Image


@dataclass(frozen=True)
class ProcessPayload:
    result: ProcessingResult
    preview_image: Image.Image


@dataclass(frozen=True)
class ExportPayload:
    path: Path
    save_as: bool


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(980, 640)

        self.loaded: LoadedImage | None = None
        self.source_analysis: ImageAnalysis | None = None
        self.result: ProcessingResult | None = None
        self.source_preview_image: Image.Image | None = None
        self.result_preview_image: Image.Image | None = None
        self.source_photo: ImageTk.PhotoImage | None = None
        self.result_photo: ImageTk.PhotoImage | None = None

        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sticker-worker")
        self.active_future: Future[object] | None = None
        self.active_operation: OperationType | None = None
        self.operation_generation = 0
        self.closing = False

        self.mode_var = tk.StringVar(value="自动")
        self.model_var = tk.StringVar(value="silueta：推荐，质量与体积平衡")
        self.background_var = tk.StringVar(value=DEFAULT_BACKGROUND_LABEL)
        self.padding_var = tk.IntVar(value=8)
        self.threshold_var = tk.IntVar(value=8)
        self.alpha_matting_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择一张 PNG、JPEG 或 WebP 图片。")
        self.source_info_var = tk.StringVar(value="来源：尚未载入图片。")
        self.result_info_var = tk.StringVar(value="结果：尚未处理。")

        self._build_widgets()
        self._bind_shortcuts()
        self._set_controls_for_operation(None)
        self.after(100, self._poll_worker)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=APP_TITLE, font=("Microsoft YaHei UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=APP_SUBTITLE).grid(row=1, column=0, sticky="w", pady=(4, 0))

        toolbar = ttk.Frame(self, padding=(14, 8, 14, 6))
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(12, weight=1)

        self.open_btn = ttk.Button(toolbar, text="选择图片", command=self.choose_image)
        self.open_btn.grid(row=0, column=0, padx=(0, 8), pady=2)
        self.process_btn = ttk.Button(toolbar, text="开始处理", command=self.process_current)
        self.process_btn.grid(row=0, column=1, padx=(0, 8), pady=2)
        self.reset_btn = ttk.Button(toolbar, text="重置", command=self.reset_state)
        self.reset_btn.grid(row=0, column=2, padx=(0, 8), pady=2)
        self.export_btn = ttk.Button(toolbar, text="导出 PNG", command=self.export_current)
        self.export_btn.grid(row=0, column=3, padx=(0, 8), pady=2)
        self.save_as_btn = ttk.Button(toolbar, text="另存为", command=self.save_as_current)
        self.save_as_btn.grid(row=0, column=4, padx=(0, 8), pady=2)
        self.open_output_btn = ttk.Button(toolbar, text="打开输出文件夹", command=self.open_output_folder)
        self.open_output_btn.grid(row=0, column=5, padx=(0, 12), pady=2)

        ttk.Label(toolbar, text="模式").grid(row=0, column=6, padx=(0, 4))
        self.mode_combo = ttk.Combobox(
            toolbar, textvariable=self.mode_var, values=list(MODE_LABELS), state="readonly", width=16
        )
        self.mode_combo.grid(row=0, column=7, padx=(0, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_ai_hint())

        ttk.Label(toolbar, text="AI 模型").grid(row=0, column=8, padx=(0, 4))
        self.model_combo = ttk.Combobox(
            toolbar, textvariable=self.model_var, values=list(MODEL_LABELS), state="readonly", width=30
        )
        self.model_combo.grid(row=0, column=9, padx=(0, 8))
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_ai_hint())

        ttk.Label(toolbar, text="预览背景").grid(row=0, column=10, padx=(0, 4))
        self.bg_combo = ttk.Combobox(
            toolbar, textvariable=self.background_var, values=list(BG_LABELS), state="readonly", width=10
        )
        self.bg_combo.grid(row=0, column=11, padx=(0, 8))
        self.bg_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_previews())

        self.progress = ttk.Progressbar(toolbar, mode="indeterminate", length=160)
        self.progress.grid(row=0, column=12, sticky="e")

        options = ttk.Frame(self, padding=(14, 2, 14, 8))
        options.grid(row=2, column=0, sticky="ew")
        ttk.Label(options, text="裁剪阈值").grid(row=0, column=0, padx=(0, 4))
        self.threshold_spin = ttk.Spinbox(options, from_=0, to=254, textvariable=self.threshold_var, width=6)
        self.threshold_spin.grid(row=0, column=1, padx=(0, 12))
        ttk.Label(options, text="透明留白").grid(row=0, column=2, padx=(0, 4))
        self.padding_spin = ttk.Spinbox(options, from_=0, to=256, textvariable=self.padding_var, width=6)
        self.padding_spin.grid(row=0, column=3, padx=(0, 12))
        self.alpha_matting_check = ttk.Checkbutton(options, text="精细边缘", variable=self.alpha_matting_var)
        self.alpha_matting_check.grid(row=0, column=4, sticky="w")

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 8))

        left = ttk.Labelframe(panes, text="原图", padding=8)
        right = ttk.Labelframe(panes, text="处理结果", padding=8)
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        self.source_label = ttk.Label(left, anchor="center", text="尚未选择图片")
        self.source_label.pack(fill=tk.BOTH, expand=True)
        self.result_label = ttk.Label(right, anchor="center", text="尚未处理")
        self.result_label.pack(fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(self, padding=(14, 0, 14, 12))
        bottom.grid(row=4, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.source_info_var, wraplength=1080).grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.result_info_var, wraplength=1080).grid(row=1, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.status_var, wraplength=1080).grid(row=2, column=0, sticky="w")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _event: self.choose_image())
        self.bind("<Control-s>", lambda _event: self.export_current())
        self.bind("<Escape>", lambda _event: self.status_var.set(""))

    def _selected_model(self) -> str:
        return MODEL_LABELS.get(self.model_var.get(), DEFAULT_MODEL)

    def _selected_mode(self) -> ProcessingMode:
        return MODE_LABELS[self.mode_var.get()]

    def _processing_options(self) -> ProcessingOptions:
        return ProcessingOptions(
            mode=self._selected_mode(),
            padding_pixels=int(self.padding_var.get()),
            alpha_crop_threshold=int(self.threshold_var.get()),
            ai_model=self._selected_model(),
            alpha_matting=bool(self.alpha_matting_var.get()),
        )

    def _make_preview_source(self, image: Image.Image) -> Image.Image:
        preview = image.convert("RGBA")
        preview.thumbnail((520, 460), Image.Resampling.LANCZOS)
        return preview

    def _operation_running(self) -> bool:
        return self.active_future is not None and not self.active_future.done()

    def _set_controls_for_operation(self, operation: OperationType | None) -> None:
        busy = operation is not None
        has_image = self.loaded is not None
        has_result = self.result is not None
        self.open_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.process_btn.configure(state=tk.NORMAL if has_image and not busy else tk.DISABLED)
        self.reset_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.export_btn.configure(state=tk.NORMAL if has_result and not busy else tk.DISABLED)
        self.save_as_btn.configure(state=tk.NORMAL if has_result and not busy else tk.DISABLED)
        self.open_output_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        combo_state = "disabled" if busy else "readonly"
        self.mode_combo.configure(state=combo_state)
        self.model_combo.configure(state=combo_state)
        self.bg_combo.configure(state=combo_state)
        self.threshold_spin.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.padding_spin.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.alpha_matting_check.configure(state=tk.DISABLED if busy else tk.NORMAL)
        if busy:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _start_operation(self, operation: OperationType, worker) -> None:
        if self._operation_running():
            return
        self.operation_generation += 1
        generation = self.operation_generation
        self.active_operation = operation
        self.active_future = self.executor.submit(worker)
        self.active_future.generation = generation  # type: ignore[attr-defined]
        self._set_controls_for_operation(operation)

    def choose_image(self) -> None:
        if self._operation_running():
            return
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")],
        )
        if not path:
            return
        self.status_var.set("正在载入并分析图片...")
        self.result = None
        self.result_preview_image = None
        self.result_photo = None
        self.result_label.configure(image="", text="尚未处理")
        self.result_info_var.set("结果：尚未处理。")

        def work() -> LoadedPayload:
            loaded = load_image(path)
            analysis = analyze_image(
                loaded.image,
                original_mode=loaded.original_mode,
                detected_format=loaded.detected_format,
            )
            return LoadedPayload(loaded, analysis, self._make_preview_source(loaded.image))

        self._start_operation(OperationType.LOAD, work)

    def process_current(self) -> None:
        if self.loaded is None or self._operation_running():
            return
        options = self._processing_options()
        if options.mode == ProcessingMode.AI and not has_cached_session(options.ai_model):
            self.status_var.set(FIRST_AI_MODEL_MESSAGE)
        else:
            self.status_var.set("正在处理...")
        loaded = self.loaded

        def work() -> ProcessPayload:
            result = process_image(
                loaded.image,
                original_mode=loaded.original_mode,
                detected_format=loaded.detected_format,
                options=options,
            )
            return ProcessPayload(result, self._make_preview_source(result.output_image))

        self._start_operation(OperationType.PROCESS, work)

    def export_current(self) -> None:
        if self.result is None or self.loaded is None or self._operation_running():
            return
        self.status_var.set("正在导出 PNG...")
        result = self.result
        source_name = self.loaded.path.name

        def work() -> ExportPayload:
            return ExportPayload(export_png(result.output_image, source_name), save_as=False)

        self._start_operation(OperationType.EXPORT, work)

    def save_as_current(self) -> None:
        if self.result is None or self.loaded is None or self._operation_running():
            return
        default_name = f"{sanitize_filename(self.loaded.path.name)}_sticker.png"
        selected = filedialog.asksaveasfilename(
            title="另存为",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG 图片", "*.png")],
            confirmoverwrite=True,
        )
        if not selected:
            return
        destination = Path(selected)
        overwrite_allowed = destination.exists()
        if overwrite_allowed and not messagebox.askyesno("确认覆盖", "目标文件已存在，是否覆盖？"):
            return
        self.status_var.set("正在另存为 PNG...")
        result = self.result

        def work() -> ExportPayload:
            return ExportPayload(
                export_png_to_path(result.output_image, destination, overwrite=overwrite_allowed),
                save_as=True,
            )

        self._start_operation(OperationType.EXPORT, work)

    def open_output_folder(self) -> None:
        try:
            out_dir = output_dir()
            out_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(out_dir)  # type: ignore[attr-defined]
        except OSError:
            LOGGER.exception("open_output_folder_failed")
            messagebox.showerror("打开失败", "无法打开输出文件夹，请查看本地日志。")

    def reset_state(self) -> None:
        if self._operation_running():
            return
        self.loaded = None
        self.source_analysis = None
        self.result = None
        self.source_preview_image = None
        self.result_preview_image = None
        self.source_photo = None
        self.result_photo = None
        self.mode_var.set("自动")
        self.model_var.set("silueta：推荐，质量与体积平衡")
        self.background_var.set(DEFAULT_BACKGROUND_LABEL)
        self.padding_var.set(8)
        self.threshold_var.set(8)
        self.alpha_matting_var.set(False)
        self.source_label.configure(image="", text="尚未选择图片")
        self.result_label.configure(image="", text="尚未处理")
        self.source_info_var.set("来源：尚未载入图片。")
        self.result_info_var.set("结果：尚未处理。")
        self.status_var.set("已重置。")
        self._set_controls_for_operation(None)

    def _poll_worker(self) -> None:
        if self.active_future and self.active_future.done():
            future = self.active_future
            operation = self.active_operation
            generation = getattr(future, "generation", None)
            self.active_future = None
            self.active_operation = None
            if generation == self.operation_generation:
                self._handle_worker_completion(operation, future)
            self._set_controls_for_operation(None)
            if self.closing:
                self._finish_close()
                return
        self.after(100, self._poll_worker)

    def _handle_worker_completion(self, operation: OperationType | None, future: Future[object]) -> None:
        try:
            payload = future.result()
        except StickerPreprocessorError as exc:
            LOGGER.info("operation_failed operation=%s code=%s", operation, exc.code)
            self.status_var.set(str(exc))
            if not self.closing:
                messagebox.showerror("操作失败", str(exc))
            return
        except Exception:
            LOGGER.exception("operation_failed operation=%s unexpected=true", operation)
            self.status_var.set("操作失败，请查看本地日志。")
            if not self.closing:
                messagebox.showerror("操作失败", "操作失败，请查看本地日志。")
            return

        if isinstance(payload, LoadedPayload):
            self.loaded = payload.loaded
            self.source_analysis = payload.analysis
            self.source_preview_image = payload.preview_image
            self.result = None
            self.result_preview_image = None
            self._update_source_info()
            self.result_info_var.set("结果：尚未处理。")
            self.status_var.set(f"已载入：{payload.loaded.path.name}")
            self.refresh_previews()
        elif isinstance(payload, ProcessPayload):
            self.result = payload.result
            self.result_preview_image = payload.preview_image
            self._update_result_info()
            self.status_var.set("处理完成。")
            self.refresh_previews()
        elif isinstance(payload, ExportPayload):
            verb = "另存为" if payload.save_as else "导出"
            self.status_var.set(f"{verb}完成：{payload.path.name}")
            if not self.closing:
                messagebox.showinfo("导出完成", f"{verb}完成：{payload.path.name}")

    def _transparency_state(self, analysis: ImageAnalysis) -> str:
        if analysis.meaningful_transparency:
            return "检测到真实透明背景"
        if analysis.has_source_alpha_channel:
            return "文件包含 Alpha 通道，但全部像素仍不透明"
        return "未检测到真实透明像素"

    def _update_source_info(self) -> None:
        if self.loaded is None or self.source_analysis is None:
            return
        analysis = self.source_analysis
        self.source_info_var.set(
            "来源："
            f"{self.loaded.path.name}；格式 {analysis.detected_format}；"
            f"{analysis.width} x {analysis.height}；{self._transparency_state(analysis)}"
        )

    def _update_result_info(self) -> None:
        if self.result is None:
            return
        result = self.result
        parts = [
            f"结果：路线 {result.selected_mode.value}",
            f"原始 {result.original_size[0]} x {result.original_size[1]}",
            f"输出 {result.output_size[0]} x {result.output_size[1]}",
            f"透明像素 {result.transparent_fraction:.1%}",
            f"耗时 {result.processing_duration:.2f} 秒",
        ]
        if result.checkerboard_analysis is not None:
            parts.append(f"棋盘格置信度 {result.checkerboard_analysis.confidence:.3f}")
        if result.warnings:
            parts.append("警告 " + "；".join(result.warnings))
        self.result_info_var.set("；".join(parts))

    def _update_ai_hint(self) -> None:
        if self._selected_mode() == ProcessingMode.AI and not has_cached_session(self._selected_model()):
            self.status_var.set(FIRST_AI_MODEL_MESSAGE)

    def refresh_previews(self) -> None:
        bg = BG_LABELS[self.background_var.get()]
        if self.source_preview_image is not None:
            preview = make_preview(self.source_preview_image, bg, (520, 460))
            self.source_photo = ImageTk.PhotoImage(preview)
            self.source_label.configure(image=self.source_photo, text="")
        if self.result_preview_image is not None:
            preview = make_preview(self.result_preview_image, bg, (520, 460))
            self.result_photo = ImageTk.PhotoImage(preview)
            self.result_label.configure(image=self.result_photo, text="")
        elif self.loaded is not None:
            self.result_label.configure(image="", text="尚未处理")

    def _on_close(self) -> None:
        if not self._operation_running():
            self._finish_close()
            return
        if not messagebox.askyesno(
            "当前任务仍在运行",
            "当前任务仍在运行。关闭后需要等待当前任务安全结束，是否继续？",
        ):
            return
        self.closing = True
        self.status_var.set("正在等待当前任务安全结束...")
        self._set_controls_for_operation(self.active_operation)

    def _finish_close(self) -> None:
        pending_cancelled = False
        if self.active_future is not None and not self.active_future.running():
            pending_cancelled = self.active_future.cancel()
        LOGGER.info("application_closing pending_cancelled=%s", pending_cancelled)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()
