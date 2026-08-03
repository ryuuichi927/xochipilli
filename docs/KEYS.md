# Xochipilli — keyboard shortcuts (canonical)

**English** | [日本語](KEYS.ja.md) | [中文](KEYS.zh.md)

**This file is canonical.** Chat suggestions disappear.  
**Only keys the designer explicitly adopts get implemented.** Do not ship “nice to have” shortcuts on your own.

**Rule:** shortcuts are disabled while a text field is focused.

---

## Implemented (adopted only)

| Key | Action | Notes |
|-----|--------|-------|
| **Space** | Play / pause | |
| **R** | Jump to track start | |
| **P** | Pin at playhead | 1st open · 2nd close |
| **K** | Play from **start of current frame** | selected segment t0 → open pin → frame under head → last frame |
| **L** | Loop selected segment ON/OFF | adopted |
| **F** | Zoom so selection fits the view | adopted |
| **Tab / Shift+Tab** | Next / previous segment | adopted |
| **← / →** | Seek 0.1 s | **Shift** = 1 s |
| **+ / −** | Zoom in / out | |
| **0** | Zoom to full track | |
| **Enter** | Focus prompt of selected segment | |
| **Del / Backspace** | Delete selected segment | |
| **⌘Z / Ctrl+Z** | Undo | last edit |
| **⌘Y / Ctrl+Y** (or **⌘⇧Z**) | Redo | restore undone change |
| Wheel | Waveform zoom | |
| **Shift+wheel** | Pan | |
| Double-click waveform | **Move playhead there** | **works inside segment frames too**. Alt+double-click = fit all |
| Click empty waveform | Seek only | pin is **P** |
| Click segment frame | Enter that segment’s edit | |

**Esc** closes the settings panel (UI chrome, not an editing command in this table).

---

## Not adopted — do not implement (memo only)

Do not code these until the designer explicitly adopts them.

| Idea | Proposed action |
|------|-----------------|
| G | Generate selected segment |
| U | Unmatch |
| \\ | Jump frame head ↔ tail |
| Esc | Clear segment selection (besides closing settings) |
| I/O etc. | Split pin roles, etc. |

---

## Change rules (strict)

1. Shortcut **suggestions** go only under “Not adopted” in this file. No code.  
2. Put a key in `app.js` **only after explicit adopt**.  
3. Never leave a proposal only in chat — write it here.  
4. i18n / settings shortcut lists show **implemented** keys only.

---

## History

- 2026-08-03: First cut. L/F/Tab adopted. Pin P · frame-head K.  
- 2026-08-03: Removed unilateral G/U/\\/Esc. Documented suggest ≠ ship.  
- 2026-08-03: ⌘Z/⌘Y undo·redo. Waveform double-click = playhead.  
- 2026-08-03: Double-click inside frame moves head. Ref image on generate.
