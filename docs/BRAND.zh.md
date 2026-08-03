# Xochipilli — 品牌标识正本

[English](BRAND.md) | [日本語](BRAND.ja.md) | **中文**

采用日：2026-08-03（三案均保留，角色固定）

| 角色 | 文件 | 来源方案 |
|------|------|----------|
| **主图标**（官方 · favicon · OS） | `static/brand/icon-primary.png` | 03 独特混合 |
| **休闲**（页眉等） | `static/brand/icon-casual.png` | 01 优雅侧颜 |
| **加载之花**（生成等待） | `static/brand/loader-flower.png` | 02 复古线描花 |

## 加载动效（方案 2）
影像生成等等待时，**屏幕中央只浮一朵花**（无卡片 / 文案）。
- 等待中：花瓣展开 **1→2→3 循环**
- 仅成功结束：**发光 → 散开**
- 失败：不散开，淡出

实现：`#genLoader` / `#flowerLoad`（`static/index.html` + `app.js` `showGenLoader`）

## 色彩
UI 金色强调靠近 `#C9A227`。默认黑底。

## UI 背景
淡淡的阿兹特克花格：`static/brand/bg-aztec-flower.svg`（`body::before` opacity ~0.045）。操作面靠面板保持可读。

## 页眉字体
**Cinzel**（候选 #1，已采用）。详见 `FONT_CANDIDATES.zh.md`。
