# Xochipilli — 本地应用启动

[English](DESKTOP.md) | [日本語](DESKTOP.ja.md) | **中文**

## 最简单
1. 点击 Dock 中的 **Xochipilli**  
   或 **应用程序** 里的 `Xochipilli.app`
2. 打开专用窗口（内容为本地 `http://127.0.0.1:8787`）

布局：
- `/Applications/Xochipilli.app`（官方图标＝方案 3）
- 代码本体：`music-film-workbench/` 的克隆目录

## 启动机制（2026-08-04 修正）
macOS **会拒绝 .app 直接 exec Documents 内的脚本**  
（症状：点击无反应 / 日志出现 `Operation not permitted`）。

因此链路为：
1. Dock → `/Applications/Xochipilli.app`
2. → 经 **osascript** 启动 `~/Library/Application Support/Xochipilli/run.sh`
3. → 用项目 `.venv` 的 Python 运行 `desktop_app.py`（pywebview 窗口）

## 其他启动方式

| 方式 | 路径 |
|------|------|
| .app | `/Applications/Xochipilli.app` |
| run.sh | `~/Library/Application Support/Xochipilli/run.sh` |
| Shell | `./RUN_DESKTOP.sh`（终端） |
| 仅浏览器 | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## 日志（打不开时）
- `~/Library/Logs/Xochipilli/launch.log`（.app 侧）
- `~/Library/Logs/Xochipilli/session.log`（Python / 窗口）

## 故障排除
- **什么都没有：** 先看上面日志。可试 `xattr -cr /Applications/Xochipilli.app` 后再点
- **Traceback / icon 参数：** `desktop_app.py` 已兼容不支持 `icon=` 的 pywebview
- **端口冲突：** 在 `.env` 设 `PORT=`，或释放 8787
- **没有 pywebview：** `.venv/bin/pip install pywebview`
