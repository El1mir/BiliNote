# WP1 维护版事实矩阵约束

锁定源：PR head 38cbdc293f43c8fdaea1f30fe91356f8fc8744e5 的 wayfinder/016-frontend-backend-mapping/report.md，已通过 git show 读取。

## 导出符号逐项字段

每条 symbol/path 必须记录 definition、caller/entry、effect、contract、test、status。status 只允许 DIRECT、DYNAMIC、BACKEND-ONLY、NOT FOUND、UNVERIFIED。TypeScript AST 口径包含直接 export、default export、named re-export，基线为 280 个唯一 pair。仅继承文件级 caller 时必须标记 UNVERIFIED，不能冒充逐符号入口证据；type-only 与 re-export 必须显式说明。

## Route 逐项字段

65 个有效 AST route 逐项记录 method/path、handler、request、response、error、service、Web caller、test、status。provider.py:75 的注释命中不计入。没有 Web caller 时标记 BACKEND-ONLY，并写明搜索边界；缺少契约或运行证据时标记 UNVERIFIED 或 NOT RUN。

## Specs 001-020 逐验收点字段

每个 acceptance point 单独记录 spec/criterion、Web symbol、route/service/contract、具名 test、browser/evidence、status/blocker。历史测试和浏览器记录只能标记 INHERITED；本轮未运行写 NOT RUN。报告现有 20 行代表性映射不等于逐 criterion 闭合。

## 本轮事实

- 锁定报告：PASS；提交存在且包含目标文件。
- CodeGraph：PASS；489 files、7,174 nodes、16,044 edges、pending 0。
- Inventory：PASS；100 tracked src files、95 runtime TS/TSX、280 exports、65 routes。
- 逐符号 caller：NOT RUN；锁定报告明确 §2B 仍为 file-level inherited。
- 逐 acceptance point：NOT RUN；当前只有代表性 spec 映射。
- 浏览器与功能测试：NOT RUN；T-046 的 run_060/run_067/run_073 只能作为继承证据。


## Specs 001-020 explicit status index

001: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
002: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
003: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
004: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
005: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
006: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
007: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
008: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
009: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
010: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
011: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
012: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
013: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
014: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
015: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
016: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
017: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
018: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
019: NOT RUN — acceptance points require explicit source/route/test/browser evidence.
020: NOT RUN — acceptance points require explicit source/route/test/browser evidence.

## 可复核边界

前端范围为 BillNote_frontend/src/ember、src/services、src/store、src/hooks、src/utils；后端范围为 backend/app/routers；规格范围为 specs/001-* 至 specs/020-*。只计 AST route decorator，排除注释命中。README 缺失或 acceptance 原文不可读时保持 BLOCKED/NOT RUN。
