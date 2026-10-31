# 020/05 · 验证与落档

- 状态：resolved
- 依赖：01–04
- 关联 spec 章节：§7、§9

## 目标

四项改动都有可复现的证据，spec 与索引同步。

## 改动点

1. 后端全量 `pytest -q`；前端 `tsc -b` / `lint` / `vitest run`。
2. 浏览器实测三项：分组滚动、批量生成设置、数学笔记渲染（用真实 `MarkdownNote` 组件渲染用户那篇笔记）。
3. 清理临时数据（12 个 `zzscroll*` 分组）与临时文件（探针脚本、临时渲染页）。
4. 更新 `specs/README.md` 索引。

## 验收

- [x] 后端 929 passed；前端 48 passed；`tsc -b` / `lint` 干净；
- [x] 三项浏览器证据截图留档；
- [x] 临时数据/文件清零；
- [x] spec 状态 implemented，README 索引已登记。
