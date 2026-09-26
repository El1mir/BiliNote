# 06 · 前端：音频转写配置页 OpenAI 兼容 ASR 管理 UI

- **依赖**：05
- **关联**：spec §3-2
- **状态**：✅ 已完成

## 改动点

`BillNote_frontend/src/pages/SettingPage/transcriber.tsx`：

1. 引擎下拉会出现 `openai-asr`（文案「OpenAI 兼容 ASR（在线）」）；
2. 选中后显示「OpenAI 兼容 ASR」卡片：
   - 多个端点列表：单选选中为当前使用、显示 `name / base_url / model`、编辑、删除、测试连接；
   - 「添加端点」表单：`name / base_url / api_key / model / timeout / max_upload_mb`；
   - 编辑时 api_key 显示打码值，未改动则不覆盖（后端已兼容带 `*` 的值）；
   - 测试连接按钮：调 `/openai_asr/{id}/test`，成功/失败 toast；
3. 保存配置时把 `transcriber_type='openai-asr'` + `openai_asr_id` 一起提交；
4. 无端点时给出引导提示（与后端就绪门禁一致）。

## 追加（2026-09-26）：端点表单改为「label + 输入框」

原来每个输入框只有 `placeholder`，而字段都有默认值 → placeholder 不显示，
用户看不出每个框是什么含义。改为统一用 `Field`（上方 `Label` + 下方 `Input` + 可选灰色说明），
并把默认值从 placeholder 里挪到 `hint`：

| 字段 | hint |
|---|---|
| 服务地址（Base URL） | 填到 /v1 为止 |
| API Key | 编辑时留空或保持打码值即不修改 |
| 超时（秒） | 默认 600 |
| 切割阈值（MB） | 超过就切成多段分别转写，默认 18 |
| 最多切片数 | 按说话切片时最多切多少段，默认 120 |
| 静音门限（dB） | 越低越不敏感；环境吵可调到 -25 |
| 最短静音（秒） | 多长的停顿算「说完了」，默认 0.5 |

## 验收

- 能添加多条、切换激活、编辑、删除；
- 切换激活 + 保存后立即对新任务生效；
- 测试连接能显示可读的成功/失败信息。
