# Design decisions

Why Xochipilli behaves the way it does. This is the public record of choices that already
shipped, kept separately from the day-to-day working log. If a decision here looks wrong,
this file is the thing to argue with.

Related: [POSITIONING.md](POSITIONING.md) (market position) · [CRAFT.md](CRAFT.md) (edit
and personalization layer) · [VIDEO_API.md](VIDEO_API.md) (provider contracts).

## The shape of the product

**Music first, video second.** The timeline and the waveform are the main line; the video
preview is subordinate. Every other decision follows from this one. A tool that starts
from the picture ends up asking the song to fit the cut.

**The human cuts the segments.** Pins define segments; each segment carries its own prompt
and its own clips. There is no "analyze the track and produce a music video" button, and
adding one would change what the tool is. Analysis produces hints, never decisions: the
emotion keywords are suggestions the author is free to ignore.

**Local workbench, not a cloud service.** FastAPI plus a static UI on the author's Mac,
optionally inside a pywebview window. Projects live outside the repo (`~/Documents/
Xochipilli` by default, `XOCHIPILLI_DATA` to override) so that updating, moving, or
re-cloning the code can never touch finished work.

**Bring your own key.** Providers are swappable (`VIDEO_PROVIDER`: `xai` / `fal` / `mock`).
The tool does not resell inference.

## Generation

**Five-second units.** Long segments are split into 5s clips (`CLIP_UNIT_SECONDS`) and
chained, rather than requesting one long take. A short pin is not collapsed into a single
15-second generation, because the pin is the author's statement about where the music
turns.

**6.7s becomes 5 + 2.** The remainder is generated as an Extension, padded to the 2s
minimum when it falls short. Durations are clamped to whole seconds on the wire (T2V 1–15,
Extension 2–10).

**Video slightly longer than music overhangs into the next segment.** When 7s of video
covers 6.7s of song, the surplus fades under the head of the next segment rather than
being trimmed. Recorded per take as `duration_plan` / `overhang_for_next` /
`video_planned_sec`.

**A failed generation is a failure.** When a real provider fails, the error surfaces. It is
never silently replaced by a mock take that looks like success. Under `mock` the user asked
for mock.

**Partial takes survive.** If a later part of a multi-part chain fails, the parts that
succeeded are kept as a partial take instead of being orphaned on disk while the UI shows
nothing.

**Camera lock and motion direction are separate intents.** Locking the camera improves
continuity when chaining, but for segments where the movement *is* the direction, a lock
lowers the ceiling. Hence `mode` (hold / shift / motion) rather than one global setting.

### Rejected

**One-click song → finished music video.** A different product on a crowded shelf. This one
is a workbench for someone who wants to make the cuts.

**Single-shot generation for anything under 15 seconds.** Briefly adopted, then reverted.
It contradicted the two decisions above: the unit is 5 seconds and the seam belongs under
the next segment, and neither is negotiable for the sake of fewer API calls.

**Craft as a private side fork.** Mode, structured Unmatch, taste memory, and partial
regeneration are standard capability. They load as separate modules (`app.server` on top of
`app.main`) for engineering clarity only.

## Data

**Series data lives in `digest.json`, not `project.json`.** Carrying the analysis series in
the project file pushed it to roughly 1MB and made every project read expensive; it is now
about 106KB. Endpoints that genuinely need features load the digest explicitly.

**Deleting keeps JSON and disk in sync.** Removing a project, segment, or take removes the
corresponding files. Clips absent from the JSON are orphans from older takes and may be
collected.

**Cold projects park in iCloud.** Untouched projects move to iCloud Drive so the local disk
gets its space back, and come back on selection. `XOCHIPILLI_COLD_DAYS` controls the delay.

## Launching on macOS

**Never exec a script inside `Documents` from the bundle.** macOS TCC blocks it, and the
failure looks like "the Dock icon does nothing". Real work happens through
`~/Library/Application Support/Xochipilli/run.sh`.

**The launcher is an in-bundle Mach-O.** WKWebView needs the process to be the app bundle
for local HTTP to be permitted. Executing Python from outside the bundle produces a window
that loads nothing while `urllib` still works — a misleading state that cost a day.

**Stock pywebview only.** Patching `setContentView_` or wrapping the web view in an NSView
container breaks clicks and resizing.

**The bundle is built, not committed.** `native/build_launcher.sh` assembles
`Xochipilli.app` from `native/Info.plist`, the launcher source, and the brand artwork.

## Interface

**The header badge shows the connected model,** for example `xAI · grok-imagine-video`,
rather than a stage label. What matters mid-session is which engine is answering.

**Timeline shortcuts are disabled while typing,** and the segment list does not re-render
under an active prompt field. Losing a half-written prompt to a background refresh is worse
than a stale badge.

**Cinzel is the header typeface,** applied to `.brand-title` only, bundled as woff2 for
offline use. The product name is never translated.

**Three UI languages** (ja / en / zh) ship in `static/i18n.js`. Multi-line strings must be
escaped; a raw newline there once took down the whole UI, so `node --check static/i18n.js`
is part of editing it.

## Known limitations

Honest about where it currently falls short:

- **Seams between chained clips** are not yet at the level of a single professional take.
  Extension conditions, end-frame quality, and when to use a technical crossfade are all
  still being tuned.
- **A distinctive drawing style tends to drift** toward the generic cinematic look that
  general-purpose models pull towards.
- **Long-chain partial regeneration exists as an API** (`regen-subclips`) but is not yet an
  obvious operation in the interface.
- **Cost is invisible.** A long segment means linearly more API calls, with no estimate
  shown before generating.
