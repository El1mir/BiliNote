# 13 · 修复 note.py 日志丢失（未接入统一 logger）

- **依赖**：—
- **关联**：spec §6
- **状态**：已完成
- **日期**：2026-09-26（实机排查 BV1E7wtzaEdq 任务时发现）

## 背景

`backend/app/services/note.py:2` 引入的是标准库 `logging`，`:68` 用
`logger = logging.getLogger(__name__)` 取得 logger，但**没有挂任何 handler**：

- 该模块所有 `logger.info(...)`（「GPT 总结并缓存成功」「已保存任务记录到数据库」
  「笔记生成成功」等关键里程碑）被 `logging` 的默认级别与空 handler 吞掉，
  `backend/logs/app.log` 里完全没有 `app.services.note` 的业务日志。
- 只有 WARNING/ERROR 通过 `logging.lastResort` 打到 stderr，且**没有时间戳/级别/模块名前缀**，
  所以在控制台上看到的是裸的 `任务异常 (task_id=...)`、`任务 ... 失败，第 1/3 次重试（5s 后）`。

用户看到的「日志停在某一步之后就没有了」有一半是这个 bug 造成的（另一半是 §14 的幻影状态文件）。

## 改动点

1. `note.py` 改用 `from app.utils.logger import get_logger` + `logger = get_logger(__name__)`，
   与其它模块一致（控制台 + `logs/app.log` 双写，`propagate=False`）。
2. 删除 `import logging` 与 `logger.setLevel(logging.INFO)`（级别由 `get_logger` 统一设置）。
3. `backend/app/routers/note.py:18` 从 `note` 模块导入的 `logger` 自动变为统一 logger，
   重试日志从此带完整前缀。

## 验收

- 生成任务时 `logs/app.log` 出现 `app.services.note - 笔记生成成功`、`已保存任务记录到数据库` 等行。
- 失败重试日志带 `YYYY-MM-DD HH:MM:SS [LEVEL] app.routers.note -` 前缀，不再是无前缀裸行。
- 不改变任何任务行为与状态写入。
