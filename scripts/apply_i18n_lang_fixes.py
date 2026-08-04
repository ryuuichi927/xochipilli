#!/usr/bin/env python3
"""Apply ZH/EN language-clean fixes to static/i18n.js.

Run from repo root:
  python3 scripts/apply_i18n_lang_fixes.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "static" / "i18n.js"

PAIRS: list[tuple[str, str]] = [
    # zh: remove Japanese mixed into Chinese UI
    ("Xochipilli / ショチピリ — 音乐电影工作台", "Xochipilli — 音乐电影工作台"),
    (
        "正本 docs/KEYS.md。建议只写在未采用栏；在明确采用前不实现。",
        "正式说明见 docs/KEYS.md。建议只写在「未采用」栏；明确采用前不要实现。",
    ),
    ("无钉 · 下次 P 开钉", "无标记点 · 下次 P 打开"),
    ("开钉 @ {t} · 下次 P 关闭", "打开标记 @ {t} · 下次 P 关闭"),
    ("取消开钉", "取消标记"),
    ("点击定位/选区间。打钉用 P", "点击定位 / 选区间。打点用 P"),
    (
        "点击波形定位，或点击区间框进入编辑。打钉用 P（播放头位置）。",
        "点击波形定位，或点击区间框进入编辑。打点用 P（播放头位置）。",
    ),
    (
        "Space · R · P 钉 · K · L · F · Tab · ⌘Z/Y · 滚轮 · 双击＝播放头（框内也可）",
        "Space · R · P 打点 · K · L · F · Tab · ⌘Z/Y · 滚轮 · 双击＝播放头（框内也可）",
    ),
    (
        "Space 播放 · R 曲头 · P 钉 · K 区间头 · L 循环 · F 适配 · Tab 下一段 · ⌘Z 撤销 · ⌘Y 重做 · ←/→ · +/- · 0 全览 · 双击定位 · Enter · Del",
        "Space 播放 · R 曲头 · P 打点 · K 区间头 · L 循环 · F 适配 · Tab 下一段 · ⌘Z 撤销 · ⌘Y 重做 · ←/→ · +/- · 0 全览 · 双击定位 · Enter · Del",
    ),
    ("还没有区间。点击时间线打钉。", "还没有区间。点击时间线打点。"),
    ("开钉 @ {t}。再点一次关闭。", "打开标记 @ {t}。再点一次关闭。"),
    ("打钉失败: {err}", "打点失败: {err}"),
    ("已取消开钉", "已取消标记"),
    # en polish
    (
        'statusGenWithRef: "generated from attached image"',
        'statusGenWithRef: "Generated from attached image"',
    ),
]


def main() -> int:
    if not TARGET.is_file():
        print(f"missing {TARGET}", file=sys.stderr)
        return 1
    text = TARGET.read_text(encoding="utf-8")
    for old, new in PAIRS:
        if old not in text:
            # already applied is OK
            if new in text:
                print(f"skip (already): {old[:40]!r}")
                continue
            print(f"MISSING: {old[:60]!r}", file=sys.stderr)
            return 1
        text = text.replace(old, new, 1)
        print(f"OK: {old[:40]!r}")
    TARGET.write_text(text, encoding="utf-8")

    # verify: no kana inside zh: { ... } block
    m = re.search(r"\n    zh: \{", text)
    if not m:
        print("zh block not found", file=sys.stderr)
        return 1
    start = m.start()
    # find matching close at indent 4
    rest = text[start:]
    # simple: until "\n    },\n  },\n};" near end of strings
    end_m = re.search(r"\n    \},\n  \},\n\};", rest)
    zh_block = rest[: end_m.start()] if end_m else rest
    kana = re.findall(r"[\u3040-\u30ff]+", zh_block)
    # allow nothing
    if kana:
        print("KANA still in zh block:", sorted(set(kana)), file=sys.stderr)
        return 1
    if "正本" in zh_block:
        print("正本 still in zh block", file=sys.stderr)
        return 1
    print(f"wrote {TARGET} — zh block clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
