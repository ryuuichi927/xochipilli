# Xochipilli（索奇皮利）

[English](README.md) | [日本語](README.ja.md) | **中文**

运行在本地电脑上的 **专业向** 音乐→影像工作台。  
名称来自阿兹特克神话中的 **Xochipilli（花之王子）**——花、歌、音乐与艺术之神。编辑界面保持安静，曲目的世界按片段逐段打开成画面。

设计：**龙一 · Ryuichi Hamakawa**

## 启动

### 桌面窗口（推荐）
```bash
cd /path/to/music-film-workbench
./RUN_DESKTOP.sh
# 或 Dock / 应用程序 中的 Xochipilli.app
```
详情：[docs/DESKTOP.zh.md](docs/DESKTOP.zh.md) · [EN](docs/DESKTOP.md) · [JA](docs/DESKTOP.ja.md)

### 仅浏览器
```bash
./RUN_ME.sh
```
打开 http://127.0.0.1:8787

## 用法要点
1. **导入曲目（消化）** — 生成分析用信号（重新导入会重置区间与片段）
2. 播放 / 定位。点击区间框进入编辑。**用 P 打点**（播放头位置）
3. 为区间写 **影像提示词**。AI 情感关键词仅供参考
4. 感觉不对 → **Unmatch**
5. **生成影像** — 在 `.env` 设置 `VIDEO_PROVIDER`（默认 `mock`）

## 键盘
**正式说明：** [docs/KEYS.zh.md](docs/KEYS.zh.md) · [EN](docs/KEYS.md) · [JA](docs/KEYS.ja.md)

Space 播放 · R 曲首 · **P** 打点 · **K** 框起点 · **L** 循环 · **F** 适配 · **Tab** · 其余见 KEYS（输入文字时无效）

## 界面语言
右上角 ⚙ — 日 / 英 / 中（`mfw.lang`）

## 影像 API（自有密钥 / SuperGrok OAuth）

**步骤说明：** [docs/VIDEO_API.zh.md](docs/VIDEO_API.zh.md) · [EN](docs/VIDEO_API.md) · [JA](docs/VIDEO_API.ja.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # 推荐（Ben's Tool SuperGrok OAuth）
# VIDEO_PROVIDER=fal   # 可选
# VIDEO_PROVIDER=mock  # 无需 API
./RUN_ME.sh
```

未配置 `.env` 时默认为 `mock`。真实提供方（`xai` / `fal`）失败时会报错，不会悄悄当成成功成片。

## 数据布局

| 路径 | 作用 |
|------|------|
| `data/projects/<id>/project.json` | 作品元数据、区间、采用片段引用（**不含完整 series**） |
| `data/projects/<id>/digest.json` | 消化详情（series、peaks 等）；服务端用于区间特征 |
| `data/projects/<id>/source.*` | 导入音源（**当前 1 份**；重导会替换） |
| `data/projects/<id>/analysis.wav` | 消化用单声道信号 |
| `data/projects/<id>/clips/` | 成片 mp4、区间音频切片、衔接帧、`program.mp4` |
| `data/projects/<id>/refs/` | 区间参考静帧（i2v） |
| `theory/` | digest / mapping 理论 JSON |
| `static/` | UI（app.js / i18n / style / brand / fonts） |
| `app/` | FastAPI 后端 |
| `docs/` | KEYS / VIDEO_API / BRAND / DESKTOP / DEV_LOG 等 |
| `tmp/` | 开发临时目录（不放成品） |

删除（设置里删项目 / 删区间 / 删成片）会保持 **JSON 与磁盘一致**。  
JSON 中没有的 clips 是孤儿文件（旧成片），需要时可清理。

## 文档一览（英 · 日 · 中）

| 内容 | English | 日本語 | 中文 |
|------|---------|--------|------|
| 本 README | [README.md](README.md) | [README.ja.md](README.ja.md) | [README.zh.md](README.zh.md) |
| 桌面启动 | [DESKTOP](docs/DESKTOP.md) | [DESKTOP.ja](docs/DESKTOP.ja.md) | [DESKTOP.zh](docs/DESKTOP.zh.md) |
| 键盘 | [KEYS](docs/KEYS.md) | [KEYS.ja](docs/KEYS.ja.md) | [KEYS.zh](docs/KEYS.zh.md) |
| 影像 API | [VIDEO_API](docs/VIDEO_API.md) | [VIDEO_API.ja](docs/VIDEO_API.ja.md) | [VIDEO_API.zh](docs/VIDEO_API.zh.md) |
| 品牌 | [BRAND](docs/BRAND.md) | [BRAND.ja](docs/BRAND.ja.md) | [BRAND.zh](docs/BRAND.zh.md) |
| 标题字体 | [FONT](docs/FONT_CANDIDATES.md) | [FONT.ja](docs/FONT_CANDIDATES.ja.md) | [FONT.zh](docs/FONT_CANDIDATES.zh.md) |
| 制作日志 | [EN 摘要](docs/DEV_LOG.en.md) | [正文 JA](docs/DEV_LOG.md) | [ZH 摘要](docs/DEV_LOG.zh.md) |
| docs 目录 | [docs/README.md](docs/README.md) | | |

## 品牌与字体
- Logo 角色：[docs/BRAND.zh.md](docs/BRAND.zh.md)（主图标=03 / 休闲=01 / 生成等待花=02）
- 标题字体：**Cinzel**（仅 `.brand-title`）— [docs/FONT_CANDIDATES.zh.md](docs/FONT_CANDIDATES.zh.md)

## 隐私
默认按 **Private** 仓库使用。不要提交 `.env`、`data/projects/` 或个人媒体（见 `.gitignore`）。

## 许可
著作权归作者所有（All rights reserved）。详见 [LICENSE](./LICENSE)（日本語 / English / 中文）。
