# ショチピリ — 映像 API の繋ぎ方

[English](VIDEO_API.md) | **日本語** | [中文](VIDEO_API.zh.md)

## プロバイダ一覧

| `VIDEO_PROVIDER` | 認証 | メモ |
|------------------|------|------|
| **`mock`**（既定） | 不要 | ローカル仮映像 |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`**（別名 `grok`） | `XAI_API_KEY`、または既存の OAuth セッション | Grok Imagine Video |

**本物プロバイダ**では失敗は **エラー**として返す（成功した成片のふりをしない）。mock は `VIDEO_PROVIDER=mock` のときだけ。

鍵は各自が用意する。他人のアカウントを経由することはない。

---

## 自分の鍵で Grok 映像を使う

### 手順

1. xAI の API キーを取得し、プロジェクトの `.env` に `XAI_API_KEY` として入れる。

   他のツールで取得済みの xAI OAuth セッションがあるなら、鍵を買わずにそれを使い回せる。
   どちらも任意で、既定では無効：

   - `XAI_OAUTH_HELPER` — `tools/xai_http.py` の `resolve_xai_http_credentials()`
     を持つディレクトリ。こちらはトークンを更新する。
   - `XAI_TOKEN_STORE` — OAuth アクセストークンを含む JSON ファイル。
     `providers.xai-oauth.tokens.access_token` を読む。更新はしないので期限切れになりうる。

2. プロジェクト `.env`:

```bash
cd /path/to/xochipilli
cp .env.example .env
```

```bash
VIDEO_PROVIDER=xai
# 任意
XAI_VIDEO_MODEL=grok-imagine-video
XAI_VIDEO_RESOLUTION=720p
XAI_VIDEO_ASPECT=16:9
# 連続性（任意）
# XAI_CHAIN_MODE=extension   # 既定。または i2v
# CLIP_UNIT_SECONDS=5
```

3. サーバ再起動:

```bash
./RUN_ME.sh
```

4. 確認（トークン本文は出ない）:

```bash
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool
```

期待:
- `video_provider`: `"xai"`
- `xai_auth.ok`: `true`
- `xai_auth.source`: `xai_api_key`、helper 設定時は `oauth-helper` など

5. UI で区間プロンプト → 生成。  
   1本 **数十秒〜数分**かかることがある。長い区間は約5秒単位に分割し、可能なら native Extension、だめなら末フレーム I2V でつなぐ。

### OAuth が切れているとき

health の `xai_auth.relogin_hint` や note に auth エラーが出る。  
セッションを管理している側で xAI に再ログインしてから `./RUN_ME.sh`。  
`XAI_API_KEY` を使っている場合はこの形で期限切れにならない。

### 認証の優先順（コード）

1. `XAI_OAUTH_HELPER` の `resolve_xai_http_credentials()`（リフレッシュ込み・設定時のみ）  
2. `XAI_API_KEY`  
3. `XAI_TOKEN_STORE` の生 `access_token`（最終手段・期限切れやすい）

---

## FAL を使う場合

```bash
VIDEO_PROVIDER=fal
FAL_KEY=...
FAL_VIDEO_MODEL=fal-ai/minimax-video
```

---

## mock に戻す

```bash
VIDEO_PROVIDER=mock
```

---

## まだ UI に無いもの

- UI からのキー入力（ブラウザに秘密を置かない）  
- 「このテイクを延長」ボタン（複数パート生成の内部では Extension 済み）  
- 区間音声を条件にした生成（主経路は text→video）

---

## コード

- `app/xai_auth.py` — OAuth / API key 解決  
- `app/video_gen.py` — 生成 + native Extension  
- `docs/VIDEO_API*.md` — 本ガイド一式
