# Spec 013: 本地转写器硬件加速与并行

- 状态：`implemented`
- 日期：2026-10-06

## 背景

用户反馈（m06758）：本地转写器（faster-whisper）运行时，本机 CPU / GPU 占用都很低，但任务进行非常慢。

根因（探查实测）：
1. **GPU 从未被启用**：`WhisperTranscriber.__init__` 的 `device` 判定走 `env_checker.is_cuda_available()`（依赖 `torch.cuda`），而部署里不装 torch，导致永远回退 CPU。
2. **CPU 并行从未生效**：`_build_model` 接受 `cpu_threads` / `num_workers` 参数但从不传给 `WhisperModel`——默认 `cpu_threads=1` 时 5 千字音频实测 **82s**，而 `threads=8` 只要 **34.8s**（约 2.4 倍差）。
3. **GPU 缺算子库**：即使显式 `device='cuda'` 加载模型成功，transcribe 时仍报 `Could not locate cudnn_ops64_9.dll ... Invalid handle`——缺 cuDNN 9 / cuBLAS 算子库，需要 pip 安装 `nvidia-cudnn-cu12` + `nvidia-cublas-cu12`，且 Python 3.8+ 不自动扫 `site-packages/nvidia/<pkg>/bin`，必须显式 `os.add_dll_directory()`。

## 目标

让「本地转写器配置」页可调硬件加速与并行，实现：
- **GPU 加速**：有 NVIDIA 显卡时默认走 CUDA（float16）。
- **CPU 并行**：可设线程数，默认自动（核数/2），显著提速。
- 配置持久化到 `transcriber.json`，保存后对新任务立即生效。

## 已定决策

1. **推理后端探测用 ctranslate2，不用 torch**：faster-whisper 的真实后端是 ctranslate2（自带 CUDA 运行时），torch 在轻量部署里可不装。`get_cuda_device_count()` 探到 GPU 才用 cuda。
2. **默认 device = "auto"**：有 GPU 用 GPU，否则 CPU。用户机器已装 GPU 算子库，`auto` 直接落到 CUDA。
3. **性能配置只对 fast-whisper 生效**：`device` / `compute_type` / `cpu_threads` / `num_workers` 四个字段仅在 `transcriber_type='fast-whisper'` 时下发并保存；mlx-whisper 忽略。
4. **compute_type 自动推导**：`auto` 在 CUDA 下 → `float16`，CPU 下 → `int8`。
5. **NVIDIA DLL 目录注册必须早于 faster-whisper 导入**：ctranslate2 首次导入即固化 DLL 搜索路径，所以 `_register_nvidia_dll_dirs()` 在 `from faster_whisper import WhisperModel` 之前执行，两头上保险（`os.add_dll_directory` + PATH 前缀）。

## 接口变更

### 配置存储（`transcriber.json`）
新增键：`whisper_device`、`whisper_compute_type`、`whisper_cpu_threads`、`whisper_num_workers`。

### 后端

- `backend/app/services/transcriber_config_manager.py`：
  - `get_config()` 增 4 个 `whisper_*` 字段（默认 `auto` / `auto` / `0` / `1`）。
  - `update_config(...)` 增 4 个可选参数，仅非 None 写入；`whisper_device` 校验 `{auto,cpu,cuda}`，`whisper_cpu_threads` `max(0, int)`，`whisper_num_workers` `max(1, int)`。
  - 新增 `get_whisper_device / get_whisper_compute_type / get_whisper_cpu_threads / get_whisper_num_workers` getter。
- `backend/app/routers/config.py`：
  - `GET /transcriber_config` 增 `local_hardware`（cpu_cores / cuda_available / gpu_name / cuda_dll_ready / device）。
  - `update_transcriber_config` 透传 4 个新字段。
- `backend/app/transcriber/whisper.py`（重写核心）：
  - `_register_nvidia_dll_dirs()`：注册 nvidia 算子库 DLL 目录。
  - `_cuda_available()`：优先 ctranslate2。
  - `resolve_device` / `resolve_compute_type`：归一化配置 → 实际参数。
  - `WhisperTranscriber.__init__`：真正把 `cpu_threads` / `num_workers` 传给 `WhisperModel`。
- `backend/app/services/note.py::_init_transcriber`：读配置透传给 `get_transcriber`。

### 前端
- `BillNote_frontend/src/services/transcriber.ts`：`TranscriberConfig` 增 4 个 `whisper_*` 字段 + `local_hardware`；`updateTranscriberConfig` 增 4 字段。
- `BillNote_frontend/src/pages/SettingPage/transcriber.tsx`：fast-whisper 时显示「推理设备 / 计算精度 / CPU 线程数 / 推理并行数」控件 + 本机硬件能力提示。

## 实测（RTX 2060 6GB / 24 逻辑核）

- CPU int8：`threads=1` → 82s，`threads=8` → 34.8s（**线程数是关键收益点**）。
- GPU float16：约 CPU 8 线程同档（tiny 模型过小，GPU 优势不明显，但随模型变大更明显）。
- 本仓库已 `pip install nvidia-cudnn-cu12 nvidia-cublas-cu12`，GPU 端到端可用。

## 测试

- `tests/test_whisper_config_forwarding.py`：断言 note 构建器把配置的 whisper 参数（含 device/compute_type/cpu_threads/num_workers）转发给 transcriber。
- `tests/test_transcriber_provider_model_selection.py`：`_Whisper.__init__` 收 `*kwargs`，并补 stub `app.transcriber.openai_asr`（修复既有 ModuleNotFoundError）。
- 全量：`tests/test_whisper_config_forwarding.py + tests/test_transcriber_provider_model_selection.py + tests/003-openai-compatible-asr/` → 51 passed；后端全量 → 653 passed；前端 build ✓。

## 待确认问题

无。
