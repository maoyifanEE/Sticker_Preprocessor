from __future__ import annotations

import logging
import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from ..exporter import export_png
from ..image_io import load_image
from ..models import (
    LoadedImage,
    PreviewBackground,
    ProcessingMode,
    ProcessingOptions,
    ProcessingResult,
    StickerPreprocessorError,
)
from ..pipeline import process_image
from ..preview import make_preview
from ..rembg_adapter import DEFAULT_MODEL

LOGGER = logging.getLogger(__name__)

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
    "网页棋盘": PreviewBackground.WEB,
}


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sticker Preprocessor")
        self.geometry("980x680")
        self.minsize(820, 560)

        self.loaded: LoadedImage | None = None
        self.result: ProcessingResult | None = None
        self.source_photo: ImageTk.PhotoImage | None = None
        self.result_photo: ImageTk.PhotoImage | None = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sticker-worker")
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.processing_future: Future[ProcessingResult] | None = None
        self.exporting = False

        self.mode_var = tk.StringVar(value="自动")
        self.model_var = tk.StringVar(value="silueta：推荐，质量与体积平衡")
        self.background_var = tk.StringVar(value="网页棋盘")
        self.padding_var = tk.IntVar(value=8)
        self.threshold_var = tk.IntVar(value=8)
        self.alpha_matting_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择一张 PNG、JPEG 或 WebP 图片。")
        self.analysis_var = tk.StringVar(value="尚未载入图片。")

        self._build_widgets()
        self._bind_shortcuts()
        self._set_busy(False)
        self.after(100, self._poll_worker)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=10)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(8, weight=1)

        self.open_btn = ttk.Button(toolbar, text="选择图片", command=self.choose_image)
        self.open_btn.grid(row=0, column=0, padx=(0, 8))
        self.process_btn = ttk.Button(toolbar, text="开始处理", command=self.process_current)
        self.process_btn.grid(row=0, column=1, padx=(0, 8))
        self.export_btn = ttk.Button(toolbar, text="导出 PNG", command=self.export_current)
        self.export_btn.grid(row=0, column=2, padx=(0, 12))

        ttk.Label(toolbar, text="模式").grid(row=0, column=3, padx=(0, 4))
        self.mode_combo = ttk.Combobox(
            toolbar, textvariable=self.mode_var, values=list(MODE_LABELS), state="readonly", width=16
        )
        self.mode_combo.grid(row=0, column=4, padx=(0, 8))

        ttk.Label(toolbar, text="AI 模型").grid(row=0, column=5, padx=(0, 4))
        self.model_combo = ttk.Combobox(
            toolbar, textvariable=self.model_var, values=list(MODEL_LABELS), state="readonly", width=28
        )
        self.model_combo.grid(row=0, column=6, padx=(0, 8))

        ttk.Label(toolbar, text="预览").grid(row=0, column=7, padx=(0, 4))
        self.bg_combo = ttk.Combobox(
            toolbar, textvariable=self.background_var, values=list(BG_LABELS), state="readonly", width=10
        )
        self.bg_combo.grid(row=0, column=8, sticky="w")
        self.bg_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_previews())

        options = ttk.Frame(self, padding=(10, 0, 10, 8))
        options.grid(row=1, column=0, sticky="ew")
        ttk.Label(options, text="裁剪阈值").grid(row=0, column=0, padx=(0, 4))
        ttk.Spinbox(options, from_=0, to=254, textvariable=self.threshold_var, width=6).grid(
            row=0, column=1, padx=(0, 12)
        )
        ttk.Label(options, text="留白像素").grid(row=0, column=2, padx=(0, 4))
        ttk.Spinbox(options, from_=0, to=256, textvariable=self.padding_var, width=6).grid(
            row=0, column=3, padx=(0, 12)
        )
        ttk.Checkbutton(options, text="精细边缘", variable=self.alpha_matting_var).grid(
            row=0, column=4, sticky="w"
        )

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.rowconfigure(2, weight=1)

        left = ttk.Labelframe(panes, text="原图", padding=8)
        right = ttk.Labelframe(panes, text="处理结果", padding=8)
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        self.source_label = ttk.Label(left, anchor="center")
        self.source_label.pack(fill=tk.BOTH, expand=True)
        self.result_label = ttk.Label(right, anchor="center")
        self.result_label.pack(fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.analysis_var, wraplength=760).grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.status_var, wraplength=760).grid(row=1, column=0, sticky="w")

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _event: self.choose_image())
        self.bind("<Control-s>", lambda _event: self.export_current())
        self.bind("<Escape>", lambda _event: self.status_var.set(""))

    def _set_busy(self, busy: bool) -> None:
        has_image = self.loaded is not None
        has_result = self.result is not None
        state = tk.DISABLED if busy else tk.NORMAL
        self.open_btn.configure(state=state)
        self.process_btn.configure(state=tk.NORMAL if has_image and not busy else tk.DISABLED)
        self.export_btn.configure(state=tk.NORMAL if has_result and not busy and not self.exporting else tk.DISABLED)
        combo_state = "disabled" if busy else "readonly"
        self.mode_combo.configure(state=combo_state)
        self.model_combo.configure(state=combo_state)
        self.bg_combo.configure(state=combo_state)

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            loaded = load_image(path)
        except StickerPreprocessorError as exc:
            LOGGER.info("validation_failed ui_message=%s", exc.code)
            messagebox.showerror("无法打开图片", str(exc))
            self.status_var.set(str(exc))
            return
        self.loaded = loaded
        self.result = None
        self.status_var.set(f"已载入：{loaded.path.name}")
        from ..analyzer import analyze_image

        analysis = analyze_image(loaded.image, original_mode=loaded.original_mode, detected_format=loaded.detected_format)
        if analysis.meaningful_transparency:
            transparency = "检测到真实透明背景"
        elif analysis.has_source_alpha_channel:
            transparency = "文件包含 Alpha 通道，但全部像素仍不透明"
        else:
            transparency = "未检测到真实透明像素"
        self.analysis_var.set(
            f"{loaded.detected_format}，{analysis.width} x {analysis.height}，{transparency}"
        )
        self.refresh_previews()
        self._set_busy(False)

    def _processing_options(self) -> ProcessingOptions:
        return ProcessingOptions(
            mode=MODE_LABELS[self.mode_var.get()],
            padding_pixels=int(self.padding_var.get()),
            alpha_crop_threshold=int(self.threshold_var.get()),
            ai_model=MODEL_LABELS.get(self.model_var.get(), DEFAULT_MODEL),
            alpha_matting=bool(self.alpha_matting_var.get()),
        )

    def process_current(self) -> None:
        if self.loaded is None or self.processing_future is not None:
            return
        self.status_var.set("正在处理...")
        self._set_busy(True)
        loaded = self.loaded
        options = self._processing_options()

        def work() -> ProcessingResult:
            return process_image(
                loaded.image,
                original_mode=loaded.original_mode,
                detected_format=loaded.detected_format,
                options=options,
            )

        self.processing_future = self.executor.submit(work)

    def _poll_worker(self) -> None:
        if self.processing_future and self.processing_future.done():
            future = self.processing_future
            self.processing_future = None
            try:
                self.result = future.result()
            except StickerPreprocessorError as exc:
                LOGGER.info("processing_failed ui_code=%s", exc.code)
                self.status_var.set(str(exc))
                messagebox.showerror("处理失败", str(exc))
            except Exception:
                LOGGER.exception("processing_failed unexpected=true")
                self.status_var.set("处理失败，请查看日志。")
                messagebox.showerror("处理失败", "处理失败，请查看日志。")
            else:
                self.status_var.set(
                    f"处理完成：{self.result.selected_mode.value}，输出 {self.result.output_size[0]} x {self.result.output_size[1]}"
                )
                self.refresh_previews()
            self._set_busy(False)
        self.after(100, self._poll_worker)

    def refresh_previews(self) -> None:
        bg = BG_LABELS[self.background_var.get()]
        if self.loaded is not None:
            preview = make_preview(self.loaded.image, bg, (430, 430))
            self.source_photo = ImageTk.PhotoImage(preview)
            self.source_label.configure(image=self.source_photo, text="")
        if self.result is not None:
            preview = make_preview(self.result.output_image, bg, (430, 430))
            self.result_photo = ImageTk.PhotoImage(preview)
            self.result_label.configure(image=self.result_photo, text="")
        elif self.loaded is not None:
            self.result_label.configure(image="", text="尚未处理")

    def export_current(self) -> None:
        if self.result is None or self.loaded is None or self.exporting:
            return
        self.exporting = True
        self._set_busy(True)
        try:
            path = export_png(self.result.output_image, self.loaded.path.name)
        except StickerPreprocessorError as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("导出失败", str(exc))
        else:
            self.status_var.set(f"已导出：{Path(path).name}")
            messagebox.showinfo("导出完成", f"已导出到 output：{Path(path).name}")
        finally:
            self.exporting = False
            self._set_busy(False)

    def _on_close(self) -> None:
        if (
            self.processing_future is not None
            and not self.processing_future.done()
            and not messagebox.askyesno("正在处理", "处理仍在进行。确定要关闭窗口吗？")
        ):
            return
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.destroy()
