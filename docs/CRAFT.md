# Craft / Taste layer

Personalization and segment craft controls for Xochipilli.

---

## 製品上の位置づけ（作者向けメモ）

**Craft は「個人用の裏パッチ」ではない。ショチピリ標準機能の一部。**

| 見方 | 内容 |
|------|------|
| **製品** | Craft 込みで一つの完成品（Xochipilli） |
| **コードの分け方** | 実装・配線の都合で `craft.py` / `taste.py` / `craft_routes.py` に分離しているだけ |
| **main との関係** | `app.main` = 映像エンジン本体。`app.server` = 本体に Craft ルートを載せて起動する入口 |

---

## Affect / Episode の設計（2026-08-04）

| 層 | 使う？ | 単位 | 意味 |
|----|--------|------|------|
| **mode** `hold\|shift\|motion` | はい | 区間 | カメラ・連鎖の物理 |
| **valence / arousal** | 任意 | 区間 | 局所の気配（次元）。20秒に載せてもよい |
| **emotion_keywords** | はい | 区間 | 音楽寄りの語・タグ |
| **Episode を区間に刻印** | **しない** | — | 理論の単位（聴取の機能・状況）とズレる |
| **Unmatch reason = `episode`** | **はい** | 判断1回 | 「求めていた体験の働きが違う」という解釈 |

`function` / `purpose` と送っても `episode` に正規化される。

---

## Endpoints (via `app.server`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/taste` | User taste memory（reason に episode 含む） |
| `PUT` | `/api/projects/{pid}/segments/{sid}/mode` | `hold` \| `shift` \| `motion` |
| `PUT` | `/api/projects/{pid}/segments/{sid}/affect` | optional `valence` / `arousal` |
| `POST` | `/api/projects/{pid}/segments/{sid}/unmatch-v2` | Structured Unmatch → taste.json |
| `POST` | `.../clips/{clip_id}/regen-subclips` | Partial subclip regen |

### Unmatch-v2 body

```json
{
  "reason": "episode",
  "editor_note": "くつろぎたかったのに煽られた",
  "editor_keywords": [],
  "valence": -0.2,
  "arousal": 0.8
}
```

`reason`: `emotion` \| `world` \| `camera` \| `style` \| **`episode`** \| `other`

---

## Modes

| Mode | Meaning | Generate behavior |
|------|---------|-------------------|
| **hold** (default) | Same scene / framing | Chain OK; camera_lock respected; Extension OK |
| **shift** | World / scene change | No chain from previous; lock off |
| **motion** | Camera may move | Chain OK; lock off |

---

## Launch

```bash
./RUN_ME.sh          # app.server:app（Craft 込み）
./RUN_DESKTOP.sh
```

## Taste storage

- Path: `data/user/taste.json` (gitignored)
- `episode_mismatch_count`, `affect_samples`, `reason_counts.episode`
- Local-only; not uploaded with the repo
- **Auto-apply (default on):** `taste.merge_prompt_fields` soft-merges repeated Unmatch signals into STYLE / NEGATIVE on generate & partial regen
- Project fields: `style`, `negative_prompt`, `apply_taste` (PATCH `/api/projects/{pid}`)
- UI: world panel + style/negative + taste toggle + gen cost estimate + subclip chips

## Prompt compose inputs (generate)

| Input | Source |
|-------|--------|
| user prompt | segment |
| world | project |
| style | project + optional taste bias |
| negative | project + optional taste bias |
| valence / arousal | segment affect |
| mode → chain/lock | craft layer |