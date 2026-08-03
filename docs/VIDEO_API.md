# ショチピリ — 映像 API の繋ぎ方

## プロバイダ一覧（D1）

| `VIDEO_PROVIDER` | 認証 | メモ |
|------------------|------|------|
| **`mock`**（既定） | 不要 | ローカル仮映像 |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`**（別名 `grok`） | **SuperGrok OAuth（Ben's Tool）** または `XAI_API_KEY` | Grok Imagine Video |

失敗時は **mock に落ちる**（区間 note に理由）。

---

## 推奨: SuperGrok Heavy → OAuth（Grok 映像）

龍一の環境は Ben's Tool が `provider: xai-oauth` / `video_gen.provider: xai` 済み。  
ショチピリは **同じ OAuth トークン**を使う（別途 API キーを買わなくてよい）。

### 手順

1. Ben's Tool 側で xAI にログインできていること  
   - Desktop の xAI / SuperGrok ログイン  
   - または CLI: `bentool auth`（xai-oauth）  
   - `~/.bentool/auth.json` に `providers.xai-oauth.tokens` がある

2. プロジェクト `.env`:

```bash
cd "/path/to/xochipilli"
cp .env.example .env
```

```bash
VIDEO_PROVIDER=xai
# 任意
XAI_VIDEO_MODEL=grok-imagine-video
XAI_VIDEO_RESOLUTION=720p
XAI_VIDEO_ASPECT=16:9
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
   1本 **数十秒〜数分**かかることがある。

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

詳細は従来どおり。

---

## mock に戻す

```bash
VIDEO_PROVIDER=mock
```

---

## まだ無いもの

- UI からのキー入力（ブラウザに秘密を置かない）  
- xAI edit / extend を区間ツールから直接叩く（生成のみ）  
- 区間音声を xAI に載せる条件生成（text→video が主）

---

## コード

- `app/xai_auth.py` — OAuth / API key 解決  
- `app/video_gen.py` — `generate_xai_clip`（`/v1/videos/generations`）  
- `docs/VIDEO_API.md` — 本ファイル  
