# Craft / Taste layer

Personalization and segment craft controls for Xochipilli.

---

## 製品上の位置づけ（作者向けメモ）

**Craft は「個人用の裏パッチ」ではない。ショチピリ標準機能の一部。**

| 見方 | 内容 |
|------|------|
| **製品** | Craft 込みで一つの完成品（Xochipilli） |
| **コードの分け方** | 実装・配線の都合で `craft.py` / `taste.py` / `craft_routes.py` に分離しているだけ |
| **ユーザーから見た名前** | 最終的には「Craft」を意識しなくてよい。UI 上は mode / Unmatch / 部分再生成として溶ける |
| **main との関係** | `app.main` = 映像エンジン本体。`app.server` = 本体に Craft ルートを載せて起動する入口。将来は main 側の pin / generate / select に完全に溶け、入口の差は消えてよい |

### なぜモジュールが分かれているか

1. 映像パイプライン（5秒分割・Extension・失敗の正直化）を先に安定させた
2. 個人化・区間の役割・部分再生成を後から安全に載せた
3. main が巨大なので、編集・学習ロジックの見通しを残した

### 完成形のイメージ

- pin / generate / select の流れに mode が自然に入る
- UI に mode・Unmatch理由・部分再生成がある
- taste（好みの蓄積）が次の生成ヒントに効く
- 起動は main だけでも全部載る（server は歴史的な入口名でも可）

### 由来

作者の要望から生まれた標準機能セット：

- Eerola 系感情キーワードに対する「なんか違う」（構造化 Unmatch）
- 使い続けるほど癖が残る（taste.json）
- 区間の役割（同じ場面 / 転換 / カメラを動かす）
- 5秒単位の部分だけ焼き直す（知る人ぞ知る操作）

### 起動

```bash
./RUN_ME.sh          # app.server:app（Craft 込み）
./RUN_DESKTOP.sh     # desktop も app.server を指すこと
```

`app.main:app` だけだと Craft ルートが載らない場合がある。起動は `app.server` を使う。

---

## Product position (EN)

**Craft is part of standard Xochipilli, not a private side fork.**

The split into `craft.py` / `taste.py` / `craft_routes.py` is an engineering boundary (stable video engine first, then edit/personalization). End users should experience one product; “Craft” is the internal name for mode, structured Unmatch, taste memory, and partial subclip regen.

`app.main` = core engine. `app.server` = core + Craft routes at boot. Over time Craft logic should sit fully inside pin / generate / select so the entry-point distinction can fade.

### Launch

```bash
./RUN_ME.sh          # app.server:app (includes Craft)
./RUN_DESKTOP.sh     # desktop should also target app.server
```

Booting `app.main:app` alone may omit Craft routes. Prefer `app.server`.

---

## Endpoints (via `app.server`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/taste` | User taste memory (Unmatch accumulation) |
| `PUT` | `/api/projects/{pid}/segments/{sid}/mode` | Set `hold` \| `shift` \| `motion` |
| `POST` | `/api/projects/{pid}/segments/{sid}/unmatch-v2` | Structured Unmatch → taste.json |
| `POST` | `/api/projects/{pid}/segments/{sid}/clips/{clip_id}/regen-subclips` | Partial subclip regen |

## Modes

| Mode | Meaning | Generate behavior |
|------|---------|-------------------|
| **hold** (default) | Same scene / framing | Previous last-frame chain OK; camera_lock respected; xAI Extension OK |
| **shift** | World / scene change | No chain from previous segment; lock forced off |
| **motion** | Camera may move | Chain OK; lock forced off |

Pin should create segments with `mode=hold` via `enrich_new_segment` when that path is wired.

## Partial regen

```bash
curl -X POST http://127.0.0.1:8787/api/projects/PID/segments/SID/clips/CLIP_ID/regen-subclips \
  -H 'Content-Type: application/json' \
  -d '{"indices":[2,3,4]}'
```

0-based indices into the 5s blocks. Take is re-stitched after.

## Taste storage

- Path: `data/user/taste.json` (gitignored)
- Local-only personalization memory; not uploaded with the repo
