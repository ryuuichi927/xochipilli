# Xochipilli — 本地应用启动

[English](DESKTOP.md) | [日本語](DESKTOP.ja.md) | **中文**

## 最简单
1. 点击 Dock 中的 **Xochipilli**  
   或 **应用程序** 里的 `Xochipilli.app`
2. 打开专用窗口（内容为本地 `http://127.0.0.1:8787`）

布局：
- `/Applications/Xochipilli.app`（官方图标＝方案 3）
- 代码本体：`ProjectRoot` 指向的克隆（例如 `~/Projects/xochipilli`）

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

## 按钮自动检查
在真实浏览器里依次点击所有按钮，并导入一首真实曲目：
```bash
.venv/bin/python -m uvicorn app.server:app --port 8788    # 另开，无令牌
.venv/bin/python tools/ui_smoke.py --port 8788 --import-file ~/path/to/track.mp3
```
它只在一个临时项目里操作并在结束时删除，不会碰到已有项目。
