# 02 合并笔记服务与批量接口

- 依赖：无（可与 01 并行）
- 关联 spec：§4 决策 3/4/5/6、§5.1
- 目标：新增纯函数合并模块与 `/generate_notes` 的 merge 字段。

## 改动点

- 新增 `backend/app/services/note_merge.py`：
  - `demote_headings(markdown, levels=1)`：代码围栏（``` / ~~~）内的行不动。
  - `build_merged_markdown(title, entries, failed, toc=True)`：`# 标题` + 目录 + 每视频 `## i. 标题`。
  - `merge_transcripts(entries)`：拼接 `full_text` 与 `segments`（段前加视频标题分隔）。
  - `build_merged_audio_meta(title, entries)`：时长求和、封面取第一条。
- `backend/app/routers/note.py` `BatchGenerateRequest` 增加 `merge` / `merge_title` / `merge_polish`；
  merge 分支：校验 items、在途拒绝、只建一条任务、`group_id=None`。
- `backend/app/gpt/universal_gpt.py` 增加 `polish_markdown(title, markdown)`（走 `_chat_completion_create`）；
  `backend/app/gpt/prompt.py` 增加 `MERGE_NOTES_PROMPT`。

## 验收

- merge=true 时 `create_group` 不被调用、`insert_video_task` 只调用一次。
- 请求体超预算时润色被跳过且保留结构拼接结果。
