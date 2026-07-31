# AGENTS.md

未来编码代理处理本仓库时必须遵守：

- 只在本仓库目录内读取、修改和生成项目文件。
- 永远不要读取、修改或集成 `Personal_Web`。
- 不要提交用户图片、截图、导出成品、模型、日志、虚拟环境或临时文件。
- 不要提交 `input`、`output`、`.runtime\reports`、`.runtime\qa-runs`、`.runtime\review-bundles` 中的运行数据。
- 测试必须使用合成图片，不能依赖真实素材。
- AI 背景移除只能通过 `sticker_preprocessor.rembg_adapter`。
- Tkinter 控件只能在主线程更新，后台线程只返回结构化结果。
- 永远保留源文件，不覆盖用户选择的输入图片。
- Alpha 质量问题优先查看结构化 JSON 报告、日志和诊断包，不要直接猜测。
- 提交前运行 `powershell -ExecutionPolicy Bypass -File .\scripts\check-project.ps1`。
- 不要直接修改、推送、合并或部署 `main`。
- 不要自动合并、发布 release 或创建 tag。

Personal_Web handoff exception:

- This repository may expose the versioned provider contract in
  `docs/contracts/` and the `--bridge-*` CLI commands.
- The provider must remain isolated: do not import Personal_Web code, call
  Personal_Web APIs, upload media, write a Personal_Web database, or modify a
  Journey canvas.
- Bridge runtime artifacts must stay under ignored `.runtime` paths.
