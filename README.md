# ショチピリ（Xochipilli）D1

ローカル PC で動く **玄人向け** 音楽→映像作業台。  
名前はアステカ神話の **Xochipilli（花の王子）** — 花と歌、音楽と芸術の神。編集画面は静かに、中身は曲の世界を区間ごとに映像へ開く。

## 起動

### デスクトップ窓（推奨・A+B）
```bash
cd "/path/to/xochipilli"
./RUN_DESKTOP.sh
# または Dock / Applications の Xochipilli.app
```
詳細: [`docs/DESKTOP.md`](docs/DESKTOP.md)

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
**正本:** [`docs/KEYS.md`](docs/KEYS.md)（チャットの提案は消えるのでここに書く）

Space 再生 · R 曲頭 · **P** ピン · **K** 枠の頭 · **L** ループ · **F** フィット · **Tab** · ほかは docs/KEYS.md（入力中は無効）

## 言語
右上 ⚙ — 日 / 英 / 中（`mfw.lang`）

## 映像 API（自分のキー / SuperGrok OAuth）

**手順の正本:** [`docs/VIDEO_API.md`](docs/VIDEO_API.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # 推奨（Ben's Tool SuperGrok OAuth）
# VIDEO_PROVIDER=fal   # 任意
# VIDEO_PROVIDER=mock  # API 不要
./RUN_ME.sh
```

工場既定（`.env` 無し）は `mock`。`xai` / `fal` 失敗時は生成が mock に落ちることがある。

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
| `tmp/` | 開発用のかす（成果物を置かない） |

削除（設定のプロジェクト削除 / 区間削除 / テイク削除）は **JSON とディスクを揃える**。  
JSON に無い clips は孤児（古いテイク）なので、必要なら GC 対象。

## 命名
`~/アイデアブック/ideas/20260803-music-film-workbench/source/naming-xochipilli.md`

## ブランド
ロゴ役割: [`docs/BRAND.md`](docs/BRAND.md)（本アイコン=03 / カジュアル=01 / 生成待ち花=02）

## ヘッダー字体
**採用中: Cinzel**（`.brand-title` のみ）。履歴と差し替え手順: [`docs/FONT_CANDIDATES.md`](docs/FONT_CANDIDATES.md)

## 制作ログ
[`docs/DEV_LOG.md`](docs/DEV_LOG.md)
