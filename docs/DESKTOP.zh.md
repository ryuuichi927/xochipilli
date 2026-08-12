# Xochipilli — 本地应用启动

[English](DESKTOP.md) | [日本語](DESKTOP.ja.md) | **中文**

## 最简单
1. 点击 Dock 中的 **Xochipilli**  
   或 **应用程序** 里的 `Xochipilli.app`
2. 打开专用窗口（内容为本地 `http://127.0.0.1:8787`）

布局：
- `/Applications/Xochipilli.app`（官方图标＝方案 3）— 只负责读取本体位置的轻量启动器
- 代码本体：`ProjectRoot` 指向的克隆（例如 `~/Projects/xochipilli`）

## 东西都放在哪里

| 内容 | 位置 | 同步 |
|------|------|------|
| 软件本体（代码 + `.venv`） | `~/Projects/xochipilli` | 仅 git |
| Dock 启动器 | `/Applications/Xochipilli.app` | 无 |
| 作品 | `~/Documents/Xochipilli/projects/<id>/` | 仅本地 |
| 口味模型 / Canva 令牌 | `~/Documents/Xochipilli/` | 仅本地 |
| 一周未打开的作品 | `iCloud Drive/Xochipilli/Archive/<id>/` | iCloud（实体已卸载） |
| 令牌 / 日志 | `~/Library/Application Support/Xochipilli/`、`~/Library/Logs/Xochipilli/` | 无 |

`.venv` 必须是**这个克隆里的实体目录**，不要指向别处的符号链接：目标一旦被删，应用就打不开。

作品放在仓库之外，这样更新或搬动代码都碰不到它。可用环境变量修改：

```bash
XOCHIPILLI_DATA=~/Documents/Xochipilli
XOCHIPILLI_ARCHIVE=~/Library/Mobile\ Documents/com~apple~CloudDocs/Xochipilli/Archive
XOCHIPILLI_COLD_DAYS=7
```

从旧的仓库内 `data/` 迁移：
```bash
.venv/bin/python tools/migrate_data.py --dry-run
.venv/bin/python tools/migrate_data.py
```

## 自动存入 iCloud（7 天规则）
一周没打开的作品会移到 iCloud Drive 并释放本地空间。它仍留在列表里，标记为 `☁`；
选中即自动取回（大文件需要几分钟）。

- 依据是「最后打开时间」，只看不改也会更新，且不算作编辑
- 流程是 **复制 → 逐个文件比对大小 → 删除本地 → `brctl evict`**，比对通过前不会删原件
- 正在导入或生成的作品、以及当前打开的作品都不会被碰
- iCloud 无法卸载尚未上传完成的文件，因此每次清理都会重试 evict

执行时机：应用启动 90 秒后一次（避免刚打开的作品被误判为冷），以及每天 04:30 由 launchd 执行
（`local.xochipilli.archive`，日志见 `~/Library/Logs/Xochipilli/archive.log`）。

手动操作：
```bash
.venv/bin/python tools/archive_cold.py --status
.venv/bin/python tools/archive_cold.py --dry-run
.venv/bin/python tools/archive_cold.py
.venv/bin/python tools/archive_cold.py --restore <id>
.venv/bin/python tools/archive_cold.py --install-agent
```

## 启动机制（0.2.x — 无 Chrome / Mach-O）
macOS **会拒绝 .app 直接 exec Documents 内的脚本**。

链路：
1. Dock → `/Applications/Xochipilli.app`
2. → **包内 Mach-O** `Contents/MacOS/Xochipilli`（嵌入 CPython）
3. → 读取 `Contents/Resources/ProjectRoot`，在该目录运行 `desktop_app.main()`
4. → 启动/复用 FastAPI（`app.server:app`）于 `:8787`
5. → **仅原生 pywebview 窗口**（不会打开 Chrome）

重建：
```bash
./native/build_launcher.sh
```

可选：`XOCHIPILLI_SHELL=browser` 时才打开系统浏览器。

## 其他启动方式

| 方式 | 路径 |
|------|------|
| .app | `/Applications/Xochipilli.app` |
| Shell | `./RUN_DESKTOP.sh`（终端） |
| 仅浏览器 | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## 日志
- `~/Library/Logs/Xochipilli/session.log`

## 故障排除
- **什么都没有：** 看 session.log；可试 `xattr -cr /Applications/Xochipilli.app`
- **Dock 立刻退出：** 运行 `./native/build_launcher.sh`，确认 ProjectRoot 路径存在
- **端口冲突：** `.env` 设 `PORT=`（不会强杀无关进程）
- **Dock 找不到 ffmpeg：** 已把 `/opt/homebrew/bin` 加入 PATH；需先 `brew install ffmpeg`
- **没有 pywebview：** `.venv/bin/pip install pywebview`
- **仅浏览器：** `XOCHIPILLI_SHELL=browser`
- **新建项目和导入都没反应（`认证令牌已过期`）：** 窗口与服务器的令牌不一致，退出重开即可。
  令牌保存在 `~/Library/Application Support/Xochipilli/api_token`
- **提示缺少音频分析库：** venv 不完整，执行 `.venv/bin/pip install -r requirements.txt` 后重启；
  启动时也会预检并提示
- **导入迟迟不结束：** iCloud Drive 上的曲目要等 macOS 下载实体，先在 Finder 打开或复制到本地
- **项目带 `☁` 且打开较慢：** 已存入 iCloud，选中会自动取回。若不想自动存放，
  可加大 `XOCHIPILLI_COLD_DAYS`，或执行 `launchctl bootout gui/$(id -u)/local.xochipilli.archive`
- **提示无法从 iCloud 取回：** iCloud Drive 未开启或归档目录已丢失，
  检查 `ls "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Xochipilli/Archive"`

## 按钮自动检查
在真实浏览器里依次点击所有按钮，并导入一首真实曲目：
```bash
.venv/bin/python -m uvicorn app.server:app --port 8788    # 另开，无令牌
.venv/bin/python tools/ui_smoke.py --port 8788 --import-file ~/path/to/track.mp3
```
它只在一个临时项目里操作并在结束时删除，不会碰到已有项目。

只检查 ☁ 取回流程：
```bash
.venv/bin/python tools/ui_smoke.py --port 8788 --only-restore
```
