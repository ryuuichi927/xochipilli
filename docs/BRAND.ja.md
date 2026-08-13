# ショチピリ / Xochipilli — ブランドマーク正本

[English](BRAND.md) | **日本語** | [中文](BRAND.zh.md)

採用日: 2026-08-03（3案すべて採用・役割固定）

| 役割 | ファイル | 元案 |
|------|----------|------|
| **本アイコン**（公式・favicon・OS） | `static/brand/icon-primary.png` | 03 独特ハイブリッド |
| **カジュアル**（ヘッダー等） | `static/brand/icon-casual.png` | 01 エレガント横顔 |
| **ローディング花**（生成待ち） | `static/brand/loader-flower.png` | 02 レトロ線画の花 |

## ローディング演出（案2）
映像生成など待ちのとき、**画面中央に花だけ**が浮く（カード・文言なし）。
- 待機中: 花びら展開 **1→2→3 をループ**
- 成功終了時のみ: **発光 → 散る**
- 失敗時: 散らずにフェードアウト

実装: `#genLoader` / `#flowerLoad`（`static/index.html` + `app.js` `showGenLoader`）

## 色
UI 金アクセント `#C9A227` に寄せる。黒地前提。

## UI 背景
うっすらアステカ花格子: `static/brand/bg-aztec-flower.svg`（`body::before` opacity ~0.045）。操作面はパネルで可読性維持。

## ヘッダー字体
**Cinzel**（採用）。ヘッダー `.brand-title` のみ — [DECISIONS.md](DECISIONS.md)。
