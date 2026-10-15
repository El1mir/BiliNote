# 01 · 单窗口网页启动与延迟加载聊天依赖

- **依赖**：无
- **关联**：spec 016 全文
- **状态**：resolved 2026-10-15

## 目标

双击根目录启动脚本后只使用一个控制台窗口；前后端并行启动，服务健康后再打开浏览器；移除启动路径上不必要的 ChromaDB 导入。

## 改动点

- 由 run.bat 在当前控制台同步调用 start-web.ps1。
- start-web.ps1 直接启动 Python 和 Node/Vite，探测 `/api/sys_check` 与前端根页；按 PID 终止其启动的进程树，不终止任意 node.exe。
- 端口已占用时显示端口和 PID 并退出，不强杀外部进程。
- 将 chat_service / VectorStoreManager 导入挪到调用它们的 chat handler 内。
- 新增启动器 smoke test 参数与聊天路由冷导入回归测试。

## 验收

- 运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { & .\run.bat -SmokeTest }"`，输出两个服务 ready，退出码 0，端口清空。
- 运行 016 测试与后端全量回归。
- 对比 `python -X importtime -c "import main"` 与启动器实测；记录实际数值，不设其他机器的硬阈值。

## Comments

- 将根目录 `run.bat` 改为在当前控制台同步调用 `start-web.ps1`；后者并行启动后端和 Vite，轮询 `/api/sys_check` 与 `http://127.0.0.1:3015/`，两者 ready 后才打开浏览器。端口已被占用时列出 PID 并退出，不会杀掉外部进程。`-SmokeTest` 用于无浏览器启动、健康检查和自动清理。
- `backend/app/routers/chat.py` 移除模块级 `chat_service` / `VectorStoreManager` 导入，在 handler 内按需导入；`backend/tests/016-web-startup-optimization/test_chat_imports_lazy.py` 在子解释器中确认导入路由后 `chromadb` 不在 `sys.modules`。
- 同环境测量：改动前 `import main` 5.568–6.277s，改动后 4.287–4.394s；旧 `/api/sys_check` ready 约 9.1s。经实际 `run.bat -SmokeTest` 入口重跑，backend ready 5.05s、frontend ready 2.16s、两者总 ready 6.14s，exit 0。启动时 Vite 自身报告 ready 约 0.8s。
- 测试：016 用例 1 passed；全后端回归 **818 passed, 2 warnings, 13 subtests passed**；`lsp_diagnostics` 对 chat router 与测试文件 clean=2；ruff clean。
- `test_chat_imports_lazy.py` 在改动前先红（导入路由确实加载 chromadb），移至 handler 后转绿。

## Answer

启动行为与冷导入优化完成。重型 RAG 依赖不再拖累无聊天需求的启动路径；前后端共用一个控制台并行启动，服务 ready 后才打开页面。
