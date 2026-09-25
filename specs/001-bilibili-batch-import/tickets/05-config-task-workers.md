# 05 · 配置：批量并发默认值

- **依赖**：无
- **关联**：spec §2-6

## 目标

把并发执行器默认值调整为 5，并写清与本地转写的关系。

## 改动点

1. `.env.example` 增加/更新 `TASK_MAX_WORKERS=5`，附注释说明本地 whisper 内存敏感、可按机器下调。
2. `backend/app/services/task_serial_executor.py` 默认值（或仅文档说明保持 env 覆盖）。
3. README 本地启动小节补充该变量。

## 验收

- 未设置 env 时按新默认运行；
- `.env.example` 有注释说明。
