# Xochipilli — 影像 API 接线

[English](VIDEO_API.md) | [日本語](VIDEO_API.ja.md) | **中文**

## 提供方一览

| `VIDEO_PROVIDER` | 认证 | 说明 |
|------------------|------|------|
| **`mock`**（默认） | 无 | 本地占位影像 |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`**（别名 `grok`） | `XAI_API_KEY`，或已有的 OAuth 会话 | Grok Imagine Video |

在 **真实提供方** 下，失败会 **直接报错**（不会悄悄当成成功成片）。只有 `VIDEO_PROVIDER=mock` 时才使用 mock。

密钥由使用者自备，不经由他人账户代理。

---

## 用自己的密钥调用 Grok 影像

### 步骤

1. 取得 xAI 的 API 密钥，写入项目 `.env` 的 `XAI_API_KEY`。

   若已在其他工具中持有 xAI 的 OAuth 会话，可以复用而无需另购密钥。
   两条路径均为可选，默认关闭：

   - `XAI_OAUTH_HELPER` — 提供 `tools/xai_http.py` 中
     `resolve_xai_http_credentials()` 的目录。此路径会刷新令牌。
   - `XAI_TOKEN_STORE` — 含 OAuth 访问令牌的 JSON 文件，读取
     `providers.xai-oauth.tokens.access_token`。不刷新，可能过期。

2. 项目 `.env`：

```bash
cd /path/to/xochipilli
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
- `xai_auth.source`: 如 `xai_api_key`，配置 helper 时为 `oauth-helper`

5. 在 UI 写区间提示词 → 生成。  
   一条可能需要 **数十秒到数分钟**。长区间会按约 5 秒切分并衔接（优先 native Extension，否则末帧 I2V）。

### OAuth 失效时

health 的 `xai_auth.relogin_hint` 或 note 中的 auth 错误。  
在管理该会话的一侧重新登录 xAI，再 `./RUN_ME.sh`。  
使用 `XAI_API_KEY` 时不会以这种方式过期。

### 认证优先级（代码）

1. `XAI_OAUTH_HELPER` 的 `resolve_xai_http_credentials()`（含刷新，仅在配置时）  
2. `XAI_API_KEY`  
3. `XAI_TOKEN_STORE` 中的原始 `access_token`（最后手段，易过期）

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
