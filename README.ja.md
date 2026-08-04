# ショチピリ（Xochipilli）

[English](README.md) | **日本語** | [中文](README.zh.md)

ローカル PC で動く **玄人向け** 音楽→映像作業台。  
名前はアステカ神話の **Xochipilli（花の王子）** — 花と歌、音楽と芸術の神。編集画面は静かに、中身は曲の世界を区間ごとに映像へ開く。

設計: **龍一 · Ryuichi Hamakawa**

## 起動

### デスクトップ窓（推奨）
```bash
cd /path/to/music-film-workbench
./RUN_DESKTOP.sh
# または Dock / Applications の Xochipilli.app
```
詳細: [docs/DESKTOP.ja.md](docs/DESKTOP.ja.md) · [EN](docs/DESKTOP.md) · [ZH](docs/DESKTOP.zh.md)

### ブラウザだけ
```bash
./RUN_ME.sh
```
http://127.0.0.1:8787

## 使い方（要点）
1. **曲を導入（消化）** — 分析用信号へ（再導入すると区間と clips はリセット）
2. 再生・シーク。区間枠クリックで編集へ。**ピンは P**（再生ヘッド）
3. 区間に **映像プロンプト**。AI 感情キーワードは参考
4. 体感と違う → **Unmatch**
5. **映像を生成** — `.env` の `VIDEO_PROVIDER`（未設定時は mock）

## キーボード
**正本:** [docs/KEYS.ja.md](docs/KEYS.ja.md) · [EN](docs/KEYS.md) · [ZH](docs/KEYS.zh.md)

Space 再生 · R 曲頭 · **P** ピン · **K** 枠の頭 · **L** ループ · **F** フィット · **Tab** · ほかは KEYS（入力中は無効）

## 言語
右上 ⚙ — 日 / 英 / 中（`mfw.lang`）

## 映像 API（自分のキー / SuperGrok OAuth）

**手順の正本:** [docs/VIDEO_API.ja.md](docs/VIDEO_API.ja.md) · [EN](docs/VIDEO_API.md) · [ZH](docs/VIDEO_API.zh.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # 推奨（Ben's Tool SuperGrok OAuth）
# VIDEO_PROVIDER=fal   # 任意
# VIDEO_PROVIDER=mock  # API 不要
./RUN_ME.sh
```

`.env` が無いときの既定は `mock`。本物プロバイダ（`xai` / `fal`）の失敗はエラーとして返し、成功した成片のふりをしない。

## データ配置

| パス | 役割 |
|------|------|
| `data/projects/<id>/project.json` | 作品メタ・区間・採用クリップ参照（**series は含めない**） |
| `data/projects/<id>/digest.json` | 消化の詳細（series・peaks 等）。サーバが区間特徴量に使う |
| `data/projects/<id>/source.*` | 導入した音源（**現行1本**。再導入で差し替え） |
| `data/projects/<id>/analysis.wav` | 消化用モノラル信号 |
| `data/projects/<id>/clips/` | テイク mp4・区間 audio 断片・連鎖フレーム・program.mp4 |
| `data/projects/<id>/refs/` | 区間の参考静止画（i2v） |
| `theory/` | digest / mapping 理論 JSON |
| `static/` | UI（app.js / i18n / style / brand / fonts） |
| `app/` | FastAPI 本体 |
| `docs/` | KEYS / VIDEO_API / BRAND / DESKTOP / DEV_LOG など |
| `tmp/` | 開発用の一時置き場（成果物を置かない） |

削除（設定のプロジェクト削除 / 区間削除 / テイク削除）は **JSON とディスクを揃える**。  
JSON に無い clips は孤児（古いテイク）なので、必要なら GC 対象。

## ドキュメント一覧（英 · 日 · 中）

| 内容 | English | 日本語 | 中文 |
|------|---------|--------|------|
| この README | [README.md](README.md) | [README.ja.md](README.ja.md) | [README.zh.md](README.zh.md) |
| デスクトップ起動 | [DESKTOP](docs/DESKTOP.md) | [DESKTOP.ja](docs/DESKTOP.ja.md) | [DESKTOP.zh](docs/DESKTOP.zh.md) |
| キーボード | [KEYS](docs/KEYS.md) | [KEYS.ja](docs/KEYS.ja.md) | [KEYS.zh](docs/KEYS.zh.md) |
| 映像 API | [VIDEO_API](docs/VIDEO_API.md) | [VIDEO_API.ja](docs/VIDEO_API.ja.md) | [VIDEO_API.zh](docs/VIDEO_API.zh.md) |
| ブランド | [BRAND](docs/BRAND.md) | [BRAND.ja](docs/BRAND.ja.md) | [BRAND.zh](docs/BRAND.zh.md) |
| ヘッダー字体 | [FONT](docs/FONT_CANDIDATES.md) | [FONT.ja](docs/FONT_CANDIDATES.ja.md) | [FONT.zh](docs/FONT_CANDIDATES.zh.md) |
| 制作ログ | [要約 EN](docs/DEV_LOG.en.md) | [DEV_LOG 本文](docs/DEV_LOG.md) | [要約 ZH](docs/DEV_LOG.zh.md) |
| docs 目次 | [docs/README.md](docs/README.md) | | |

## ブランド・字体
- ロゴ役割: [docs/BRAND.ja.md](docs/BRAND.ja.md)（本アイコン=03 / カジュアル=01 / 生成待ち花=02）
- ヘッダー字体: **Cinzel**（`.brand-title` のみ）— [docs/FONT_CANDIDATES.ja.md](docs/FONT_CANDIDATES.ja.md)

## プライバシー
既定は **Private** リポジトリ想定。`.env`・`data/projects/`・個人メディアはコミットしない（`.gitignore` 参照）。

## ライセンス
`LICENSE` を後から足すまで、著作権は作者に帰属します。
