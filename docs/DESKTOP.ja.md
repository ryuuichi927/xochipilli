# ショチピリ — ローカルソフト起動

[English](DESKTOP.md) | **日本語** | [中文](DESKTOP.zh.md)

## いちばん簡単
1. **Dock の Xochipilli** をクリック  
   または **アプリケーション** の `Xochipilli.app`
2. 専用窓が開く（中身はローカル `http://127.0.0.1:8787`）

配置:
- `/Applications/Xochipilli.app`（公式アイコン＝案3）
- 実体コード: `music-film-workbench/` のクローン先

## 起動の仕組み（2026-08-04 夜）
macOS は **.app から Documents 内を直接 exec すると拒否**する。

鎖:
1. Dock → `/Applications/Xochipilli.app`
2. → **`exec`** `~/Library/Application Support/Xochipilli/run.sh`（プロセスは生き残る）
3. → `desktop_app.py` が `:8787` を起動／再利用
4. → **Chrome 系 `--app=http://127.0.0.1:8787/`** で本番 UI  
   だめなら Safari → 最後に pywebview

**pywebview 単体に戻さない理由:** この Mac では WKWebView が **真っ白**のまま（サーバは HTML を正しく返していた）。  
詳細: [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md)

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

健全な session の目安:
```text
exec run.sh (stay as app process)
… desktop_app start …
reuse server …（または server ready）
window created → http://127.0.0.1:8787
```

## トラブル
- **何も起きない:** 上記ログを確認。一度 `xattr -cr /Applications/Xochipilli.app` のあと再クリック
- **Dock が跳ねてすぐ終わる:** ランチャがまだ nohup+exit になっていないか確認
- **真っ白な窓（タイトルだけ）:** WKWebView が URL を描けていない。暗い bootstrap + `load_html(..., base_uri=…)` で対処。詳細は [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md)。session.log に `load_html ok` が出るのが健全
- **Traceback / icon 引数:** `desktop_app.py` は icon 非対応版 pywebview 向けに修正済み
- **ポート衝突:** `.env` の `PORT=` または既存 8787
- **pywebview 無し:** `.venv/bin/pip install pywebview`
- **Ben's Tool の PYTHONPATH 混入:** run.sh で解除。desktop_app も `/.bentool/` を sys.path から落とす
