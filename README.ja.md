# ショチピリ（Xochipilli）

[English](README.md) | **日本語** | [中文](README.zh.md)

手作業を前提にした、ローカルで動く 音楽→映像の作業台。曲がタイムラインで、要る区間を人が
ピンで切り、区間ごとに演出を書き、テイクは自分のディスクに残る。

「曲を入れたら MV が出てくる」ボタンは無い。付けたら別の道具になる。
名前はアステカ神話の **Xochipilli（花の王子）** — 歌・踊り・芸術の神。

設計: **龍一 · Ryuichi Hamakawa**

## 曲を導入する

導入したばかりの曲は、波形以外に何も無い。

![導入直後。波形だけの状態](docs/media/digest-before.png)

消化（digest）は曲を読んで、区間の候補を出す。下の金色の帯がそれで、ここでは 21 本、
librosa の novelty 検出による。操作は **Apply section drafts** というボタンなので、
採用しても、置き換えても、放っておいて自分でピンを打ってもいい。候補を出すところで
止める理由は [DECISIONS.md](docs/DECISIONS.md) にある。

![消化後。波形の上に区間候補が乗った状態](docs/media/digest-after.png)

## 区間ひとつを演出する

![区間エディタ。プロンプト、区間モード、任意の Feel、2本のテイク、そしてモデルへ送られた時間窓](docs/media/segment.png)

大きな入力欄は自分のもので、画を決めているのはここだけ。その上にある機械の寄与は
**AI emotion (reference)** と明示されている。4語、無視してよい。**Segment mode** は
ここでは `Hold`、同じ場面と画面構成という意味で、だからカメラ固定を掛けても安全になる。
`Shift` と `Motion` は逆のことを言う。**Feel** の2本は、動かさなければ未設定のまま。

生成ボタンは **`Generate another take · ~4 API calls`** と出る。この区間は 15.4 秒で
単位が5秒なので、1テイクが連鎖4本、`4×5s` と記録される。ここに写っている2本は同じ区間に
対して生成したもので、通るまで重ねるのが普段の使い方。連鎖のうち1本だけが外れたときは
**Partial regen** が番号付きの部分 `0 1 2 3` から選んだものだけを撮り直すので、途中の
1秒のために通った3本を捨てずに済む。

最後の行が、モデルに実際に渡されたもの。

> TIME WINDOW – This is part 1 of 4 of a 15.4-second sequence, covering seconds 0.0–5.0.
> Depict ONLY the events that belong to this time window. Do not compress …

画のほうが曲の時計に合わせる。5秒ずつ。

## 現状

**開発中 — `0.1.0-d1`、stage D1。** 2026年8月開始、いまも動いている。実作業には使って
いるが、他人向けに包装されていない。準備は Python 仮想環境と `ffmpeg`、それに自分の API
キーが要る。連鎖クリップの継ぎ目は、まだプロの一発の水準に届かない。

足りていない点は [DECISIONS.md § Known limitations](docs/DECISIONS.md#known-limitations) に
並べてある。

## 考えたことが書いてある場所

この問題について自分が整理できたことは、コードよりも次の3つの文書に入っている。

| 文書 | 内容 |
|------|------|
| [DECISIONS.md](docs/DECISIONS.md) | 実装済みの判断、その理由、試して捨てた道、現在の限界 |
| [POSITIONING.md](docs/POSITIONING.ja.md) | 近隣ツールの調査と、どこも出していない組み合わせ |
| [RESEARCH-CONTEXT.md](docs/RESEARCH-CONTEXT.md) | 自分の聴取研究が設計に入った唯一の場所と、入れなかった場所 |

## 起動

### デスクトップ窓（推奨）
```bash
cd /path/to/xochipilli
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

## 映像 API（キーは自分のものを使う）

**手順の正本:** [docs/VIDEO_API.ja.md](docs/VIDEO_API.ja.md) · [EN](docs/VIDEO_API.md) · [ZH](docs/VIDEO_API.zh.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # Grok Imagine（XAI_API_KEY が必要）
# VIDEO_PROVIDER=fal   # 任意
# VIDEO_PROVIDER=mock  # API 不要
./RUN_ME.sh
```

`.env` が無いときの既定は `mock`。本物プロバイダ（`xai` / `fal`）の失敗はエラーとして返し、成功した成片のふりをしない。

## 開発

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest        # デスクトップ殻の契約 + digest フェーズ確認
./native/build_launcher.sh        # Xochipilli.app を再ビルド（成果物。git には入れない）
```

## データ配置

作品は **リポジトリの外** に置く。コードを更新・移動・再クローンしても作品に触れない。
既定は `~/Documents/Xochipilli`（`XOCHIPILLI_DATA` で変更）。以下の `<data>` はその場所。

| パス | 役割 |
|------|------|
| `<data>/projects/<id>/project.json` | 作品メタ・区間・採用クリップ参照（**series は含めない**） |
| `<data>/projects/<id>/digest.json` | 消化の詳細（series・peaks 等）。サーバが区間特徴量に使う |
| `<data>/projects/<id>/source.*` | 導入した音源（**現行1本**。再導入で差し替え） |
| `<data>/projects/<id>/analysis.wav` | 消化用モノラル信号 |
| `<data>/projects/<id>/clips/` | テイク mp4・区間 audio 断片・連鎖フレーム・program.mp4 |
| `<data>/projects/<id>/refs/` | 区間の参考静止画（i2v） |
| iCloud `Xochipilli/Archive/` | 長く開いていない作品の退避先（`XOCHIPILLI_COLD_DAYS`） |
| `theory/` | digest / mapping 理論 JSON |
| `static/` | UI（app.js / i18n / style / brand / fonts） |
| `app/` | FastAPI 本体 |
| `docs/` | KEYS / VIDEO_API / BRAND / DESKTOP / DECISIONS など |

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
| 設計判断 | [DECISIONS](docs/DECISIONS.md) | — | — |
| ポジション | [POSITIONING](docs/POSITIONING.md) | [POSITIONING.ja](docs/POSITIONING.ja.md) | — |
| 研究文脈 | [RESEARCH-CONTEXT](docs/RESEARCH-CONTEXT.md) | — | — |
| Craft / taste 層 | [CRAFT](docs/CRAFT.md) | — | — |
| プロンプトの書き方 | [PROMPTING](docs/PROMPTING.md) | — | — |
| docs 目次 | [docs/README.md](docs/README.md) | | |

## ブランド・字体
- ロゴ役割: [docs/BRAND.ja.md](docs/BRAND.ja.md)（本アイコン=03 / カジュアル=01 / 生成待ち花=02）
- ヘッダー字体: **Cinzel**（`.brand-title` のみ）— [docs/DECISIONS.md](docs/DECISIONS.md)

## ライセンス
著作権は作者に帰属します（All rights reserved）。
使用・複製・再配布の許諾は与えていません。
詳細は [LICENSE](./LICENSE)（日本語 / English / 中文）。
