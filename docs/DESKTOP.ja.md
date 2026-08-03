# ショチピリ — ローカルソフト起動

[English](DESKTOP.md) | **日本語** | [中文](DESKTOP.zh.md)

## いちばん簡単
1. **Dock の Xochipilli** をクリック  
   または **アプリケーション** の `Xochipilli.app`
2. 専用窓が開く（中身はローカル `http://127.0.0.1:8787`）

配置:
- `/Applications/Xochipilli.app`（公式アイコン＝案3）
- 実体コード: `music-film-workbench/` のクローン先

## 起動の仕組み（2026-08-04 修正）
macOS は **.app から Documents 内スクリプトを直接 exec すると拒否**する  
（症状: クリックしても無反応 / ログに `Operation not permitted`）。

そのため:
1. Dock → `/Applications/Xochipilli.app`
2. → `~/Library/Application Support/Xochipilli/run.sh` を **osascript 経由**で起動
3. → `.venv` の Python で `desktop_app.py`（pywebview 窓）

## 他の起動手段

| 手段 | パス |
|------|------|
| .app | `/Applications/Xochipilli.app` |
| run.sh | `~/Library/Application Support/Xochipilli/run.sh` |
| シェル | `./RUN_DESKTOP.sh`（ターミナルから） |
| ブラウザのみ | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## ログ（起動しないとき）
- `~/Library/Logs/Xochipilli/launch.log`（.app 側）
- `~/Library/Logs/Xochipilli/session.log`（Python / 窓）

## トラブル
- **何も起きない:** 上記ログを確認。一度 `xattr -cr /Applications/Xochipilli.app` のあと再クリック
- **Traceback / icon 引数:** `desktop_app.py` は icon 非対応版 pywebview 向けに修正済み
- **ポート衝突:** `.env` の `PORT=` または既存 8787
- **pywebview 無し:** `.venv/bin/pip install pywebview`
