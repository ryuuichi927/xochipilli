# Xochipilli — 影像 API 接线

[English](VIDEO_API.md) | [日本語](VIDEO_API.ja.md) | **中文**

## 提供方一览

| `VIDEO_PROVIDER` | 认证 | 说明 |
|------------------|------|------|
| **`mock`**（默认） | 无 | 本地占位影像 |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`**（别名 `grok`） | **SuperGrok OAuth（Ben's Tool）** 或 `XAI_API_KEY` | Grok Imagine Video |

在 **真实提供方** 下，失败会 **直接报错**（不会悄悄当成成功成片）。只有 `VIDEO_PROVIDER=mock` 时才使用 mock。

---

## 推荐：SuperGrok → OAuth（Grok 影像）

若 Ben's Tool 已配置 `provider: xai-oauth` / `video_gen.provider: xai`，  
Xochipilli 会复用 **同一 OAuth 令牌**（不必另购 API 密钥）。

### 步骤

1. 在 Ben's Tool 侧完成 xAI 登录  
   - Desktop 的 xAI / SuperGrok 登录  
   - 或 CLI：`bentool auth`（xai-oauth）  
   - `~/.bentool/auth.json` 中有 `providers.xai-oauth.tokens`

2. 项目 `.env`：

```bash
cd /path/to/music-film-workbench
cp .env.example .env
```

```bash
VIDEO_PROVIDER=xai
# 可选
XAI_VIDEO_MODEL=grok-imagine-video
XAI_VIDEO_RESOLUTION=720p
XAI_VIDEO_ASPECT=16:9
# 连续性（可选）
# XAI_CHAIN_MODE=extension   # 默认；或 i2v
# CLIP_UNIT_SECONDS=5
```

3. 重启服务：

```bash
./RUN_ME.sh
```

4. 检查（不会打印令牌正文）：

```bash
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool
```

期望：
- `video_provider`: `"xai"`
- `xai_auth.ok`: `true`
- `xai_auth.source`: 如 `bentool-oauth`

5. 在 UI 写区间提示词 → 生成。  
   一条可能需要 **数十秒到数分钟**。长区间会按约 5 秒切分并衔接（优先 native Extension，否则末帧 I2V）。

### OAuth 失效时

health 的 `xai_auth.relogin_hint` 或 note 中的 auth 错误。  
在 **Ben's Tool 重新登录 xAI**，再 `./RUN_ME.sh`。

### 认证优先级（代码）

1. Ben's Tool `resolve_xai_http_credentials`（含刷新）  
2. `XAI_API_KEY`  
3. `auth.json` 中的原始 `access_token`（最后手段，易过期）

---

## 使用 FAL

```bash
VIDEO_PROVIDER=fal
FAL_KEY=...
FAL_VIDEO_MODEL=fal-ai/minimax-video
```

---

## 回到 mock

```bash
VIDEO_PROVIDER=mock
```

---

## 界面上尚未具备

- 从 UI 输入密钥（秘密不进浏览器）  
- 「延长此成片」按钮（多分段生成内部已使用 Extension）  
- 以区间音频条件生成（主路径仍是 text→video）

---

## 代码

- `app/xai_auth.py` — OAuth / API key 解析  
- `app/video_gen.py` — 生成 + native Extension  
- `docs/VIDEO_API*.md` — 本指南三语
