# Canva Connect（ショチピリ → Canva）

音楽の世界を形にしたあとの **仕上げ** 用。生成コアは触らない。

## できること

1. 設定で **Canva に接続**（OAuth PKCE）
2. **Canva に送る** で次をアップロード
   - 優先: `program.mp4`（結合書き出し済み）
   - なければ: 選択中区間の採用クリップ
3. 画像（手描き ref）は API でデザイン作成まで試行
4. **動画** は Canva 素材庫（Projects）へ。API は動画をデザイン上に自動配置できないので、Canva 側で置く

## セットアップ

1. [Canva Developers → Integrations](https://www.canva.com/developers/integrations) で integration 作成  
2. Redirect URL: `http://127.0.0.1:8787/api/canva/callback`  
3. Scopes: `asset:read` `asset:write` `design:content:write` `design:meta:read` `profile:read`  
4. `.env` に:

```bash
CANVA_CLIENT_ID=...
CANVA_CLIENT_SECRET=...
CANVA_REDIRECT_URI=http://127.0.0.1:8787/api/canva/callback
```

5. `./RUN_ME.sh` 再起動 → 設定 → **Canva に接続** → **Canva に送る**

トークンは `data/canva_tokens.json`（gitignore）。

## API

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/canva/status` | 接続状態 |
| GET | `/api/canva/authorize` | OAuth URL |
| GET | `/api/canva/callback` | redirect |
| POST | `/api/canva/disconnect` | 切断 |
| POST | `/api/projects/{id}/canva/send` | body: `{what, segment_id?, clip_file?, open_design}` |

`what`: `program` | `segment_active` | `clip` | `ref`
