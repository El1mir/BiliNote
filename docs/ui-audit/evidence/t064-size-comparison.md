# T-064 产物体积对比（pnpm build）

| 指标 | 移除前 | 移除后 | 变化 |
| --- | --- | --- | --- |
| dist 总大小（du -sk） | 4174 KB | 4173 KB | -1 KB |
| dist 文件数 | 76 | 75 | -1 |
| dist/assets/*.js 合计 | 1713 KB | 1712 KB | -1 KB |
| JS chunk 数 | 11 | 10 | -1（animation chunk 消失） |

说明：这 13 个包在 src/ 里本来就没有被 import，Rollup 因此从未把它们打进产物 —— 唯一的可见变化是
vite.config.ts manualChunks 里那两个只含死依赖的 chunk 名（ui 里的 antd/@ant-design/x 其实从未生效，
animation 只由 lottie 两个包组成、移除后整个 chunk 消失）。所以体积变化只有 1 KB 量级，
真正的收益在安装体积：`pnpm remove` 一次移除 43 个包（含 antd 全家桶等传递依赖）。

移除前后 chunk 明细（dist/assets/*.js）：

| chunk | 移除前 (B) | 移除后 (B) |
| --- | --- | --- |
| index | 536828 | 537180 |
| markdown | 795408 | 795408 |
| math | 258429 | 258429 |
| vendor | 49704 | 49704 |
| SettingsPage | 49660 | 49660 |
| ui | 22133 | 21733 |
| OnboardingPage | 8660 | 8656 |
| transcriber | 1078 | 1078 |
| event | 1436 | 1436 |
| core | 195 | 195 |
| animation | 60 | （chunk 消失） |

index 的 +352B 与 OnboardingPage 的 -4B 是 hash/分块边界移动导致的正常抖动，不是本卡引入的代码变化。