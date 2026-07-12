# Sticker_Preprocessor

## 项目目的

Sticker_Preprocessor 是一个独立的本地 Windows 桌面应用，用于把普通图片、已有透明背景图片、以及把透明棋盘格烘进像素里的图片，转换成干净、紧凑裁剪、真正透明的 RGBA PNG 贴纸文件。

## 与 Personal_Web 的关系

本项目与 `Personal_Web` 完全独立。它不会读取、修改、调用、部署或上传到 `Personal_Web`。输出 PNG 以后可以由用户手动选择并上传到其他项目。

## 功能

- 选择单张 PNG、JPEG 或 WebP 图片。
- 自动分析真实 Alpha、内嵌棋盘格和普通不透明背景。
- 支持自动、真实透明清理、棋盘格移除、AI 去背景四种处理模式。
- 显示原图和结果预览，并支持浅色、深色、网页渐变背景。
- 默认预览不使用棋盘格，避免把真实透明和假棋盘格再次混淆。
- 默认导出到 `output`，也可以另存为指定 PNG。
- 可打开输出文件夹。
- 本地日志写入 `.runtime\logs`。

## 支持的输入

- PNG
- JPEG
- WebP

不支持 SVG、GIF、APNG、动态 WebP、视频、远程 URL、损坏图片和超限图片。Pillow 的 decompression-bomb 防护触发时会按“图片尺寸过大”处理。

## 三种处理路线

- 真实透明清理：保留原始 RGBA，仅裁剪透明边界并清理 Alpha 为 0 的 RGB。
- 内嵌棋盘格移除：保守识别灰白棋盘格，支持任意裁剪偏移 phase，只移除与边界连通的候选背景。
- AI 去背景：通过可选 `rembg[cpu]` 本地 CPU 推理处理普通不透明背景。

## 环境要求

- Windows
- Python `>=3.11,<3.14`，本机可使用 Python 3.12.2
- Tkinter
- 至少 4 GB 可用磁盘空间用于完整 AI 安装
- AI 处理时建议至少 4 GB 可用内存

不需要 GPU、CUDA、Docker、Node.js、Web 服务或数据库。

## 安装

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Dev
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -SkipAI -Dev
```

安装脚本按顺序探测 `py -3.12`、`py -3.11`、`py -3.13`、`python`，选择兼容的 64 位解释器并确认 Tkinter 可用。脚本只创建仓库内 `.venv`，并使用 `pip install --no-cache-dir`。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

也可以双击 `Start Sticker Preprocessor.cmd`。

## UI 操作

- `选择图片`：后台解码、应用 EXIF 方向、转换 RGBA 并分析透明度。
- `开始处理`：后台执行透明清理、棋盘格移除或 AI 去背景。
- `重置`：清空当前图片、结果、预览和诊断，不删除已导出文件或模型缓存。
- `导出 PNG`：后台保存到 `output`，重名时自动编号。
- `另存为`：选择一个 PNG 目标路径，存在文件会确认覆盖。
- `打开输出文件夹`：打开仓库内 `output` 目录。

加载、分析、处理、AI 模型初始化和 PNG 编码验证都在单个后台 worker 中执行。Tk 主线程只负责文件对话框、控件更新、消息框和预览呈现。

关闭窗口时如果任务仍在运行，应用会询问是否继续关闭；确认后会等待当前任务安全结束，再关闭窗口。

## 预览背景

- 浅色：`#F4F1EA`
- 深色：`#252A34`
- 网页背景：浅蓝到奶油色渐变

预览背景只影响界面显示，不会修改真实输出 PNG。原图和结果始终使用同一个选中的预览背景。

## 首次 AI 模型下载说明

首次使用 AI 模式时，`rembg` 会把模型下载到 `.runtime\models\rembg`。模型不进入 Git，可能占用较多本地磁盘空间。界面只提示首次模型使用需要下载，不显示字节级下载百分比。

## 输出目录

默认输出到 `output`。除 `output\.gitkeep` 外，导出的 PNG 被 `.gitignore` 忽略。

## 输出 PNG 规范

- PNG
- RGBA
- 包含真实非不透明 Alpha
- 不覆盖原图
- 文件名会清理 Windows 非法字符
- 默认导出重名时自动追加序号
- 另存为会通过确认流程避免静默覆盖

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m sticker_preprocessor --self-check
.\.venv\Scripts\python.exe -m sticker_preprocessor --ui-smoke-test
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1
```

AI smoke test 会使用真实模型缓存：

```powershell
.\.venv\Scripts\python.exe -m sticker_preprocessor --ai-smoke-test --model silueta
```

普通 pytest 不下载模型，测试图片均为合成图。

## 隐私与本地处理

图片在本地处理。应用不调用云端背景移除 API，不上传图片，不写入 Personal_Web，不需要账户。

## 当前限制

- V1 只支持单图处理。
- 不提供手动画笔或蒙版编辑。
- 不提供 EXE、MSI 或自动更新。
- AI 结果和边缘质量仍需要人工视觉复核。
- 建议在浅色、深色和网页背景下检查透明效果。
