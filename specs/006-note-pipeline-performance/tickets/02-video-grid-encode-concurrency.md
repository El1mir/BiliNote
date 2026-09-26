# 02 · 网格拼接与 base64 编码并发 + 编码进度

- **依赖**：—
- **关联**：spec §4 决策 5–6
- **状态**：已完成

## 目标

`video_reader.py` 的拼图与编码是本次最长的纯 CPU 静默段（实测 45 组 / 400 帧，数分钟且无任何进度）。

## 改动点

1. `VideoReader.run()`：
   - 统一进度分母 `total_units = len(groups) + len(image_paths)`；
   - 拼图用 `ThreadPoolExecutor` 并发调用 `concat_images()`（保序），每完成一组 `current += 1`；
   - `encode_images_to_base64()` 改为并发读文件 + 编码（保序），每完成一张 `current += 1`；
   - 两者都通过现有 `progress_callback("building_grids", current, total, message)` 回报，
     message 分别形如「正在拼接第 i/n 组网格图」「正在编码第 i/n 张图像」。
2. `concat_images()` 本身不改语义（仍是 PIL 逐张粘贴 + save），只把调用搬到线程里。
3. 失败时保留原异常行为（并发体异常直接抛出，由 `run()` 的调用方处理）。
4. 并发度取 `min(8, os.cpu_count() or 4)`；单组/单张时退化为串行路径。

## 验收

- 网格图文件数量、命名与内容与改动前一致；`video_img_urls` 顺序不变。
- 拼图/编码期间前端 `building_grids` 阶段进度持续推进，不出现长时间静止。
- 合成小图（例如 9 帧 / 3 组）的单元测试产出与串行实现逐字节一致。
