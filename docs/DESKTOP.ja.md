# ショチピリ — ローカルソフト起動

[English](DESKTOP.md) | **日本語** | [中文](DESKTOP.zh.md)

## いちばん簡単
1. **Dock の Xochipilli** をクリック  
   または **アプリケーション** の `Xochipilli.app`
2. 専用窓が開く（中身はローカル `http://127.0.0.1:8787`）

配置:
- `/Applications/Xochipilli.app`（公式アイコン＝案3）
- 実体コード: `ProjectRoot` が指すクローン（例: `~/Projects/xochipilli`）

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
