# Xochipilli（索奇皮利）

[English](README.md) | [日本語](README.ja.md) | **中文**

以手工为前提、运行在本地电脑上的 音乐→影像工作台。曲子就是时间线：由人打点切出要用的
区间，逐段写下调度，成片留在自己的磁盘上。

没有「丢进一首歌就吐出 MV」的按钮；加上它就是另一个产品了。
名称来自阿兹特克神话中的 **Xochipilli（花之王子）** — 歌、舞与艺术之神。

设计：**龙一 · Ryuichi Hamakawa**

## 当前状态

**开发中 — `0.1.0-d1`，stage D1。** 2026 年 8 月开始，仍在持续开发。它能跑，作者也在用它做
实际工作，但尚未为他人打包。安装是开发者流程（Python 虚拟环境、`ffmpeg`、自备 API 密钥），
连接片段之间的接缝还达不到专业一条过的水准。

不足之处诚实地列在
[DECISIONS.md § Known limitations](docs/DECISIONS.md#known-limitations)。

公开的目的是让设计与理由可以被阅读，而不是因为软件已经完成。

## 建议先读

如果目的是了解这个项目而不是运行它，要点是这三份。

| 文档 | 内容 |
|------|------|
| [DECISIONS.md](docs/DECISIONS.md) | 已落地的每个决定、理由、试过又放弃的路线，以及当前的局限 |
| [POSITIONING.md](docs/POSITIONING.md) | 邻近工具的调研，以及没有任何一家做出的那个组合 |
| [RESEARCH-CONTEXT.md](docs/RESEARCH-CONTEXT.md) | 作者的日常聆听研究影响了设计的哪一处，以及在哪里被刻意拒绝 |

## 启动

### 桌面窗口（推荐）
```bash
cd /path/to/xochipilli
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

## 影像 API（使用自备密钥）

**步骤说明：** [docs/VIDEO_API.zh.md](docs/VIDEO_API.zh.md) · [EN](docs/VIDEO_API.md) · [JA](docs/VIDEO_API.ja.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # Grok Imagine（需要 XAI_API_KEY）
# VIDEO_PROVIDER=fal   # 可选
# VIDEO_PROVIDER=mock  # 无需 API
./RUN_ME.sh
```

未配置 `.env` 时默认为 `mock`。真实提供方（`xai` / `fal`）失败时会报错，不会悄悄当成成功成片。

## 开发

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest        # 桌面外壳契约 + digest 阶段检查
./native/build_launcher.sh        # 重新构建 Xochipilli.app（构建产物，不入 git）
```

## 数据布局

作品保存在 **仓库之外**：更新、移动或重新 clone 代码都不会碰到它。
默认根目录为 `~/Documents/Xochipilli`（可用 `XOCHIPILLI_DATA` 覆盖）。下表的 `<data>` 指该目录。

| 路径 | 作用 |
|------|------|
| `<data>/projects/<id>/project.json` | 作品元数据、区间、采用片段引用（**不含完整 series**） |
| `<data>/projects/<id>/digest.json` | 消化详情（series、peaks 等）；服务端用于区间特征 |
| `<data>/projects/<id>/source.*` | 导入音源（**当前 1 份**；重导会替换） |
| `<data>/projects/<id>/analysis.wav` | 消化用单声道信号 |
| `<data>/projects/<id>/clips/` | 成片 mp4、区间音频切片、衔接帧、`program.mp4` |
| `<data>/projects/<id>/refs/` | 区间参考静帧（i2v） |
| iCloud `Xochipilli/Archive/` | 长期未打开的作品会移到这里以释放本地磁盘（`XOCHIPILLI_COLD_DAYS`） |
| `theory/` | digest / mapping 理论 JSON |
| `static/` | UI（app.js / i18n / style / brand / fonts） |
| `app/` | FastAPI 后端 |
| `docs/` | KEYS / VIDEO_API / BRAND / DESKTOP / DECISIONS 等 |

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
| 设计决策 | [DECISIONS](docs/DECISIONS.md) | — | — |
| 市场定位 | [POSITIONING](docs/POSITIONING.md) | [POSITIONING.ja](docs/POSITIONING.ja.md) | — |
| 研究背景 | [RESEARCH-CONTEXT](docs/RESEARCH-CONTEXT.md) | — | — |
| Craft / taste 层 | [CRAFT](docs/CRAFT.md) | — | — |
| 提示词写法 | [PROMPTING](docs/PROMPTING.md) | — | — |
| docs 目录 | [docs/README.md](docs/README.md) | | |

## 品牌与字体
- Logo 角色：[docs/BRAND.zh.md](docs/BRAND.zh.md)（主图标=03 / 休闲=01 / 生成等待花=02）
- 标题字体：**Cinzel**（仅 `.brand-title`）— [docs/DECISIONS.md](docs/DECISIONS.md)

## 个人笔记的处理
开发日记、事故记录与计划笔记都不放在本仓库中。不要提交 `.env`、导入的音源，或任何包含本机
绝对路径的文件（见 `.gitignore`）。

## 许可
著作权归作者所有（All rights reserved）。
公开仅供阅读与评估，不授予使用、复制或再分发的许可。
详见 [LICENSE](./LICENSE)（日本語 / English / 中文）。
