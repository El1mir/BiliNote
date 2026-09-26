# 07 · 测试

- **依赖**：01-06
- **关联**：全部
- **状态**：✅ 已完成

## 改动点

`backend/tests/003-openai-compatible-asr/`：

1. `test_config_manager.py`：
   - 端点 CRUD 持久化；删除 active 清空 `openai_asr_id`；
   - `get_public_config()` 打码；`update` 时带 `*` 的 key 不覆盖；
   - 字段校验（缺 model / 非正 timeout 报错）。
2. `test_openai_asr_transcriber.py`：
   - mock OpenAI client：`verbose_json` 正常解析出 segments；
   - mock 只支持 `json` 的返回 → 退化为单段；`text` 同理；
   - 文件超阈值时调用压缩（mock `compress_audio`）；
   - 空 api_key 抛可读错误。
3. `test_ready_gate.py`：`openai-asr` 未配置端点 → `ready=False`。

前端：`BillNote_frontend/tests/003-openai-compatible-asr/`（若交互逻辑可抽纯函数则加，
否则依赖现有 `pnpm build` + 人工验收）。

## 验收

- `pytest` 全绿；新增用例覆盖上述分支。
