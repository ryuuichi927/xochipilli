# ショチピリ — ローカルソフト起動

[English](DESKTOP.md) | **日本語** | [中文](DESKTOP.zh.md)

## いちばん簡単
1. **Dock の Xochipilli** をクリック  
   または **アプリケーション** の `Xochipilli.app`
2. 専用窓が開く（中身はローカル `http://127.0.0.1:8787`）

配置:
- `/Applications/Xochipilli.app`（公式アイコン＝案3）— 本体の場所を読むだけの薄いランチャ
- 実体コード: `ProjectRoot` が指すクローン（例: `~/Projects/xochipilli`）

## どこに何が置いてあるか

| もの | 場所 | 同期 |
|------|------|------|
| ソフト本体（コード + `.venv`） | `~/Projects/xochipilli` | git のみ |
| Dock のランチャ | `/Applications/Xochipilli.app` | なし |
| 制作した作品 | `~/Documents/Xochipilli/projects/<id>/` | ローカルのみ |
| 味の学習 / Canva トークン | `~/Documents/Xochipilli/` | ローカルのみ |
| 1週間開いてない作品 | `iCloud Drive/Xochipilli/Archive/<id>/` | iCloud（実体はオフロード） |
| トークン / ログ | `~/Library/Application Support/Xochipilli/`, `~/Library/Logs/Xochipilli/` | なし |

`.venv` は**このクローンの中に実体で**置く（他所へのシンボリックリンクにしない）。
リンクにすると、リンク先を消した瞬間にアプリが起動しなくなる。

作品はリポジトリの外に出してある。コードを更新したり別の場所に置き直したりしても、
作ったものに手が届かないようにするため。置き場所は環境変数で変えられる:

```bash
XOCHIPILLI_DATA=~/Documents/Xochipilli        # 作品
XOCHIPILLI_ARCHIVE=~/Library/Mobile\ Documents/com~apple~CloudDocs/Xochipilli/Archive
XOCHIPILLI_COLD_DAYS=7                        # 何日開かなければ退避するか
```

昔のクローン内 `data/` から引っ越すには:
```bash
.venv/bin/python tools/migrate_data.py --dry-run   # 何が動くか見る
.venv/bin/python tools/migrate_data.py
```

## iCloud への自動退避（7日ルール）
開いてから7日たった作品は iCloud Drive に移り、ローカルの実体は解放される。
一覧には `☁` 付きで残り、選べばその場で取り戻す（大きい曲だと数分かかる）。

- 判定は「最後に開いた日」。見るだけでも日付は更新される（編集扱いにはしない）
- 移動は **コピー → 全ファイルの大きさ照合 → ローカル削除 → `brctl evict`** の順。
  照合が通るまで元は消さない
- 導入や生成の最中の作品、いま開いている作品には触らない
- iCloud はアップロード完了前の実体を解放できないので、毎回の掃除でもう一度 evict を試す

実行のタイミング:
- アプリ起動から90秒後に一度（最初に開いた作品が「冷たい」と誤判定されないため）
- 毎日 04:30 に launchd で（`local.xochipilli.archive`、ログは `~/Library/Logs/Xochipilli/archive.log`）

手で操る:
```bash
.venv/bin/python tools/archive_cold.py --status          # どれが☁でどれがローカルか
.venv/bin/python tools/archive_cold.py --dry-run         # 何が退避されるか
.venv/bin/python tools/archive_cold.py                   # いま退避する
.venv/bin/python tools/archive_cold.py --restore <id>    # 取り戻す
.venv/bin/python tools/archive_cold.py --install-agent   # 日次の仕掛けを入れ直す
```

## 起動の仕組み（0.2.x — Chrome なし / Mach-O）
macOS は **.app から Documents 内を直接 exec すると拒否**する。

鎖:
1. Dock → `/Applications/Xochipilli.app`
2. → **バンドル内 Mach-O** `Contents/MacOS/Xochipilli`（埋め込み CPython）
3. → `Contents/Resources/ProjectRoot` を読み、そこで `desktop_app.main()` を実行
4. → FastAPI（`app.server:app`）を `:8787` で起動／再利用
5. → **ネイティブ pywebview 窓だけ**（Chrome は開かない）

再ビルド:
```bash
./native/build_launcher.sh
```
（repo の `.app` と、あれば `/Applications/Xochipilli.app` に Mach-O + ProjectRoot を同期）

任意: `XOCHIPILLI_SHELL=browser` のときだけシステムブラウザ。  
以前の Chrome `--app` プロファイルは起動時に停止する。

詳細: [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md)

## 他の起動手段

| 手段 | パス |
|------|------|
| .app | `/Applications/Xochipilli.app` |
| シェル | `./RUN_DESKTOP.sh`（ターミナルから） |
| ブラウザのみ | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## ログ（起動しないとき）
- `~/Library/Logs/Xochipilli/session.log`（ランチャ / Python / uvicorn）

健全な session の目安:
```text
==== mach-o launcher … root=…/xochipilli ====
… desktop_app start …
reuse server …（または server ready）
using load_html shell …
```

## トラブル
- **何も起きない:** `session.log` を確認。一度 `xattr -cr /Applications/Xochipilli.app` のあと再クリック
- **Dock が跳ねてすぐ終わる:** `./native/build_launcher.sh` で Mach-O を再ビルド。`ProjectRoot` のパスが存在するか確認
- **真っ白な窓（タイトルだけ）:**
  1. まずブラウザで http://127.0.0.1:8787/ が暗く見えるか確認（見える＝サーバ OK）
  2. `session.log` に `using load_html shell` があるか
  3. Dock `.app` 経由か確認（素の python だと WK の localhost が弱い）
  詳細: [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md)
- **ポート衝突:** `.env` の `PORT=`。無関係プロセスは殺さない（自前 uvicorn のみ停止）
- **ffmpeg が見つからない（Dock）:** Homebrew の `/opt/homebrew/bin` を PATH に足す処理済み。未インストールなら `brew install ffmpeg`
- **pywebview 無し:** `.venv/bin/pip install pywebview`
- **ブラウザで開きたいときだけ:** `XOCHIPILLI_SHELL=browser`（Dock 既定では開かない）
- **新規プロジェクトも曲の導入も効かない（`認証トークンが古い`）:** 窓が持っているトークンと
  サーバのトークンがずれている。アプリを終了して開き直す。トークンは
  `~/Library/Application Support/Xochipilli/api_token` に永続化されるので、次からはずれない
- **`音声解析ライブラリが足りない (…)`:** `.venv` が中途半端。
  `cd <project> && .venv/bin/pip install -r requirements.txt` のあと再起動。
  起動時にも検査して同じ内容を知らせる
- **導入が何分も終わらない:** iCloud Drive 上の曲は macOS が実体をダウンロードするまで進まない。
  Finder でその曲を開いて実体化させるか、ローカルにコピーしてから導入する
- **一覧に `☁` が付いていて開くのが遅い:** iCloud に退避してある。選べば自動で戻る。
  戻したくないなら `XOCHIPILLI_COLD_DAYS` を大きくするか、
  `launchctl bootout gui/$(id -u)/local.xochipilli.archive` で日次を止める
- **`iCloud から取り戻せなかった`:** iCloud Drive がオフか、退避先の実体が消えている。
  `ls "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Xochipilli/Archive"` で中身を確認

## ボタンの自動確認
UI の全ボタン（フォルダへ飛ぶ / 新規作成 / 改名 / 削除 / 書き出し）と曲の導入を
実ブラウザで一気に押して確認する:
```bash
.venv/bin/python -m uvicorn app.server:app --port 8788    # 別窓（トークン無し）
.venv/bin/python tools/ui_smoke.py --port 8788 --import-file ~/path/to/track.mp3
```
使い捨てプロジェクトを作ってその中だけで試し、最後に消すので既存プロジェクトは触らない。

☁ からの取り戻しだけを確かめる:
```bash
.venv/bin/python tools/ui_smoke.py --port 8788 --only-restore
```
