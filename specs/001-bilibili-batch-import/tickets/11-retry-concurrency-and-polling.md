# 11 · 重试也要防并发 + 状态轮询误判

- **依赖**：09
- **关联**：spec §12（并发隔离），⚠️ 修订 09
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 现象（真实日志）

同一个任务被**并发跑了两遍**，并伴随错误：

```
13:52:51 请求转录器类型: openai-asr      ← 两次
13:52:51 写入状态文件 ... PENDING        ← 两次
13:52:51 写入状态文件失败：Permission denied: 'note_results\...status.tmp'
INFO: POST /api/generate_note            ← 两次
```

日志里还能看到 DOWNLOADING / TRANSCRIBING 状态**来回跳**、yt-dlp 重复下载、
120 段静音切片被跑了两轮。

## 根因链

1. 抽帧/转写时后端 CPU 打满（8 路并发 ffmpeg + 上百次 ASR 请求），
   前端 `axios` **全局 timeout 只有 10s** → 偶发的状态轮询超时；
2. `useTaskPolling` 的 catch 里**任何一次失败都把任务标成 `FAILED`**：
   ```ts
   } catch (e) {
     updateTaskContent(task.id, { status: 'FAILED' })   // ← 单次抖动就判死
   }
   ```
   而且 `get_task_status` 还会弹一个「笔记生成失败」的 toast；
3. 界面因此出现「重试」按钮 → 用户点击 → 带**同一个 task_id** 重新提交；
4. 后端 `generate_note` 的进行中检查是
   `if not data.task_id and _is_task_in_flight(...)` —— **重试分支直接跳过了检查**，
   于是同一个 task_id 被并发执行两遍；
5. 两个进程抢同一个 `{task_id}.status.tmp` → `Permission denied`。

> 补充：后端并没有真正「阻塞到不返回」——日志里 status 请求基本都在 200 OK。
> 触发点是**客户端 10s 超时**，不是服务端无响应。

## 修复

### 后端
1. `_is_task_id_in_flight(task_id)`：直接读该 task_id 的状态文件判断是否在跑；
2. `generate_note` 的重试分支加检查：任务仍在跑 → 返回
   `task_in_progress`（code 300103），不再重复起任务；
3. `_update_status` 的临时文件加唯一后缀
   （`{name}.{8位随机}.tmp`），即使并发也不会抢同一个文件。

### 前端
4. `request.ts` 全局 timeout **10s → 30s**；
5. `useTaskPolling`：改为**连续失败 5 次**才判定任务失败，
   成功一次就清零；失败期间只 `console.warn`，不误判、不弹 toast；
6. `get_task_status`：轮询失败不再弹「笔记生成失败」，改由上层统一处理。

## 测试

- `tests/001-bilibili-batch-import/test_retry_dedup.py`：
  各种进行中状态（PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/SAVING）
  判定为在跑；SUCCESS/FAILED/未知状态判定为不在跑；坏 JSON 与空 id 安全返回 False。

## 验收

- 任务进行中再次点「重试」会被拒绝（`task_in_progress`），不会并发跑两遍；
- 单次状态轮询超时不再把任务误标为失败；
- 后端繁忙时前端不再报「网络问题」。
