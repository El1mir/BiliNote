# 020/04 · 分组区可滚动

- 状态：resolved
- 依赖：无
- 关联 spec 章节：§4 决策 7、§6.3

## 目标

分组多时能滚、最后一行不被裁成半行，且滚动不会带动整页。

## 改动点

`BillNote_frontend/src/ember/features/workspace/GroupPanel.tsx`：

- `<section>` 加 `shrink-0`（rail 是 flex 列，不加会被 TaskList 压扁）；
- 列表容器 `max-h-[264px]` → `max-h-[min(45vh,420px)]`，加 `overscroll-contain`。

## 验收

- [x] 14 个分组时 `scrollHeight 494 > clientHeight 380`，`scrollTop` 可到 114（= max）；
- [x] 滚到底可见最后一组与「未分组」；
- [x] 临时分组已清理，真实分组数量未变。
