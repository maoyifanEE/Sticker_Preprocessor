# Sticker_Preprocessor

## 项目目的

Sticker_Preprocessor 是一个独立的本地 Windows 桌面应用，用于把普通图片、已有透明背景图片、以及把透明棋盘格烘进像素里的图片，转换成干净、紧凑裁剪、真正透明的 RGBA PNG 贴纸文件。

## 与 Personal_Web 的关系

本项目与 `Personal_Web` 完全独立。它不会读取、修改、调用、部署或上传到 `Personal_Web`。输出 PNG 以后可以由用户手动选择并上传到其他项目。

## 功能

- 选择单张 PNG、JPEG 或 WebP 图片。
- 自动分析真实 Alpha、内嵌棋盘格和普通不透明背景。
- 支持自动、真实透明清理、棋盘格移除、AI 去背景四种处理模式。
- 显示原图和结果预览。
- 导出真正透明的 RGBA PNG。
- 本地日志写入 `.runtime\logs`。

## 支持的输入

- PNG
- JPEG
- WebP

不支持 SVG、GIF、APNG、动态 WebP、视频、远程 URL、损坏图片和超限图片。

## 三种处理路线

- 真实透明清理：保留原始 RGBA，仅裁剪透明边界并清理 Alpha 为 0 的 RGB。
- 内嵌棋盘格移除：保守识别灰白棋盘格，只移除与边界连通的候选背景。
- AI 去背景：通过可选 `rembg[cpu]` 本地推理处理普通不透明背景。

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

## 首次 AI 模型下载说明

首次使用 AI 模式时，`rembg` 会把模型下载到 `.runtime\models\rembg`。模型不进入 Git，可能占用较多本地磁盘空间。

## 输出目录

默认输出到 `output`。除 `output\.gitkeep` 外，导出的 PNG 被 `.gitignore` 忽略。

## 输出 PNG 规范

- PNG
- RGBA
- 包含真实非不透明 Alpha
- 不覆盖原图
- 文件名会清理 Windows 非法字符
- 重名时自动追加序号

## UI 操作说明

- `Ctrl+O`：选择图片
- `Ctrl+S`：导出当前有效结果
- `Escape`：清理临时状态

处理前必须先选择图片。导出按钮只在处理成功后启用。

## 常见问题

- AI 模式提示未安装：重新运行安装脚本，不带 `-SkipAI`。
- 首次 AI 很慢：模型需要首次下载并初始化。
- 浅色边缘效果不好：尝试其他模型或启用精细边缘。
- 棋盘格未识别：检测器偏保守，避免误删主体，请改用 AI。

## 测试

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m sticker_preprocessor --self-check
.\.venv\Scripts\python.exe -m sticker_preprocessor --ui-smoke-test
powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1
```

AI smoke test 会下载真实模型：

```powershell
.\.venv\Scripts\python.exe -m sticker_preprocessor --ai-smoke-test --model silueta
```

## 隐私与本地处理

图片在本地处理。应用不调用云端背景移除 API，不上传图片，不写入 Personal_Web，不需要账户。

## 项目结构

```text
src/sticker_preprocessor
  image_io.py          输入验证和解码
  analyzer.py          Alpha 分析
  alpha_tools.py       透明裁剪
  checkerboard.py      棋盘格检测和移除
  rembg_adapter.py     AI 适配层
  pipeline.py          处理决策树
  exporter.py          PNG 导出
  ui/main_window.py    Tkinter UI
```

## 当前限制

- V1 只支持单图处理。
- 不提供手动画笔或蒙版编辑。
- 不提供 EXE、MSI 或自动更新。
- AI 结果需要人工视觉复核。
- 建议在浅色和深色预览背景下检查透明效果。
