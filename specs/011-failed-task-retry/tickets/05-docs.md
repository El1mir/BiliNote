# 工单 05 · README 与文档

- **状态**：已完成
- **依赖**：工单 01–04

> 这份文档本身是否会把凭据写进仓库？—— 盘点文案时只引用占位符字面量（`Bearer your-api-key` 等），不写入任何真实密钥。实测见 spec §7。

## 验收清单

- [x] `specs/011-failed-task-retry/spec.md`（状态 `implemented`）
- [x] `specs/011-failed-task-retry/tickets/01–05`
- [x] `specs/README.md` 表格新增 011 行
- [x] 更新 `specs/011.../spec.md` §7「验证」表格，填入**实测**结果而非预期值
- [x] §7.1 记录本轮修掉的三个缺陷：`NOTE_OUTPUT_DIR` 双所有者、`missing` 可能未绑定、`?p=0` 无效地址

## 实测数据来源

| 项 | 命令 |
| --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` |
| spec 011 目录 | `cd backend; .venv\Scripts\python.exe -m pytest tests/011-failed-task-retry -q` |
| 前端测试 | `cd BillNote_frontend; pnpm test` |
| 前端构建 | `cd BillNote_frontend; pnpm build` |
| 前端类型 | `cd BillNote_frontend; pnpm exec tsc -p tsconfig.app.json --noEmit` |
| pi-lens | `lens_diagnostics mode=full paths=[...]`（`refreshRunners=cheap`） |

> [!IMPORTANT]
> 前端类型门禁必须传 `-p tsconfig.app.json`。根 `BillNote_frontend/tsconfig.json` 是
> solution 式配置（`{"files": [], "references": [...]}`），不传 `-p` 时 `tsc` 只解析
> 空文件集 → **恒 exit 0、零输出**。这是 spec 007 验收时踩到的坑，见
> [007 §13](../../007-note-archive-and-media-cache/spec.md)。
