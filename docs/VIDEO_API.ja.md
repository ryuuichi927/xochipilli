# ショチピリ — 映像 API の繋ぎ方

[English](VIDEO_API.md) | **日本語** | [中文](VIDEO_API.zh.md)

## プロバイダ一覧

| `VIDEO_PROVIDER` | 認証 | メモ |
|------------------|------|------|
| **`mock`**（既定） | 不要 | ローカル仮映像 |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`**（別名 `grok`） | **SuperGrok OAuth（Ben's Tool）** または `XAI_API_KEY` | Grok Imagine Video |

**本物プロバイダ**では失敗は **エラー**として返す（成功した成片のふりをしない）。mock は `VIDEO_PROVIDER=mock` のときだけ。

---

## 推奨: SuperGrok → OAuth（Grok 映像）

Ben's Tool が `provider: xai-oauth` / `video_gen.provider: xai` 済みなら、  
ショチピリは **同じ OAuth トークン**を使う（別途 API キーを買わなくてよい）。

### 手順

1. Ben's Tool 側で xAI にログインできていること  
   - Desktop の xAI / SuperGrok ログイン  
   - または CLI: `bentool auth`（xai-oauth）  
   - `~/.bentool/auth.json` に `providers.xai-oauth.tokens` がある

2. プロジェクト `.env`:

```bash
cd /path/to/music-film-workbench
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
- `xai_auth.source`: `bentool-oauth` など

5. UI で区間プロンプト → 生成。  
   1本 **数十秒〜数分**かかることがある。長い区間は約5秒単位に分割し、可能なら native Extension、だめなら末フレーム I2V でつなぐ。

### OAuth が切れているとき

health の `xai_auth.relogin_hint` や note に auth エラーが出る。  
**Ben's Tool で xAI 再ログイン**してから `./RUN_ME.sh`。

### 認証の優先順（コード）

1. Ben's Tool `resolve_xai_http_credentials`（リフレッシュ込み）  
2. `XAI_API_KEY`  
3. `auth.json` の生 `access_token`（最終手段・期限切れやすい）

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
