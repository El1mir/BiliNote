# 09 · 过大的音频改为「切割多段」而不是压缩

- **依赖**：01-08
- **关联**：spec §3-5、§4.1，⚠️ 修订 02/08
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

02 / 08 对「音频超过阈值」的处理是**整段压缩**（压成 64k mp3，必要时再压 32k）。
用户要求改成**切割**：超过阈值就切成多段分别转写，再把结果合并；同时把参数从
「压缩阈值」改成「**切割阈值**」。

## 已定语义

| 项 | 旧 | 新 |
|---|---|---|
| 字段名 | `max_upload_mb` | **`chunk_size_mb`**（旧配置里的 `max_upload_mb` 仍能读，自动映射） |
| 超阈值行为 | ffmpeg 压成 mp3（64k → 32k） | **切成 N 段分别转写再合并** |
| UI 文案 | 压缩阈值（MB） | **切割阈值（MB）** |
| 默认值 | 18 | 18 |

切割规则：

1. `N = ceil(文件大小 / 阈值)`；`chunk_size_mb` 阈值先按字节算，且**下限 256KB**（避免切太碎）；
2. 每段时长 `= 音频总时长 / N`，且**不低于 10s**；总时长探测失败时退化为每段 600s；
3. `N > 200` 直接报可读错误（提示先手动拆分），不无限切；
4. 切割优先 **stream copy（不重新编码）**；容器不支持时退回按 64k 重新编码成 mp3；
5. 每段独立请求；合并时：
   - 分段按**累计偏移**平移时间戳（`start/end += offset`），`offset` 取前几段的实际时长之和；
   - `full_text` 由各段文本拼接；`language` 取第一个非空值；
6. `chat` 风格（MiMo）额外受 **base64 10MB 上限**约束：阈值取 `min(chunk_size_mb, 7.5MB)`。

## 改动点

### 后端
1. `utils/audio_helper.py`：新增 `split_audio(input_path, segment_seconds)`
   （先 `-c copy`，失败退回 `libmp3lame -b:a 64k`；返回 `(chunk_paths, temp_dir)`）；
2. `transcriber/openai_asr.py`：
   - 删除 `_prepare_upload` / `_prepare_for_chat` 等压缩逻辑；
   - 新增 `_transcribe_in_chunks` / `_merge` / `_chunk_limit_bytes`；
   - 单段时行为保持不变（不重建 full_text）；
3. `TranscriberConfigManager`：字段 `max_upload_mb` → `chunk_size_mb`（含旧配置兼容）；
4. `transcriber_provider` / `routers/config.py`：同步改名。

### 前端
5. `services/transcriber.ts` 与转写配置页：字段改名 + 文案改「切割阈值（MB）」。

## 测试

- `test_openai_asr_transcriber.py`：超阈值时调用 `split_audio`、两段请求、时间戳偏移合并、
  切割临时目录被清理、段数超上限报错、chat 风格按 7.5MB 上限切割；
- `test_split_audio.py`（新增，真实 ffmpeg）：wav 切 3 段、mp3 也能切、总时长守恒；
- `test_config_manager.py`：字段改名 + 旧 `max_upload_mb` 兼容映射。

## 验收

- 音频超过切割阈值时切成多段并全部转写，合并后文本完整、时间戳连续；
- 不再对音频做整段压缩；
- 旧配置（`max_upload_mb`）无需手动迁移即可继续使用。
