# 01 · 后端：高价值帧采样算法

- **依赖**：无
- **关联**：spec §3-2、§4.1
- **状态**：✅ 已完成

## 目标
提供「画面变化 + 字幕分段」两路信号合并的高价值抽帧时间点计算。

## 改动点
1. 新增 `backend/app/utils/frame_sampler.py`：
   - `detect_scene_timestamps()`：ffmpeg `select='gt(scene,0.4)',showinfo`，正则解析 `pts_time`；
   - `_dedupe_by_second()`：按秒去重、排序、过滤非法值；
   - `_downsample_evenly()`：超上限按时间均匀降采样，保留首尾；
   - `select_smart_timestamps()`：合并场景/字幕信号 → 去重 → 截断到 `max_frames`。

## 验收
- 场景检测失败返回 `[]`，不抛异常；
- 同一秒的场景+字幕点只保留一个；
- 超过 `max_frames` 时结果长度等于上限且含首尾。

## 测试
`backend/tests/002-video-understanding-sampling/test_frame_sampler.py`
