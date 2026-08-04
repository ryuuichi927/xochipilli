/* Music Film Workbench D1 — client + i18n */

const $ = (id) => document.getElementById(id);
const LANG_KEY = "mfw.lang";

const state = {
  project: null,
  audioUrl: null,
  raf: null,
  selectedSegId: null,
  lang: "ja",
  /** Visible time window on the waveform (seconds). Null end = full track until known. */
  viewStart: 0,
  viewEnd: null,
  lastPinTime: null,
  loopSegId: null,
  syncMusic: true,
  previewSegId: null,
  previewClipFile: null,
  genInflight: new Set(),
  drag: null,
  playRate: 1,
  /** "program" = full adopted combo; "segment" = single selected segment lock */
  previewMode: "program",
  _videoSwitching: false,
  _scrollSync: false,
  _scrollDragging: false,
  /** Front layer key: "A" | "B" (double-buffer) */
  frontKey: "A",
  /** filename -> object URL (Blob cache for adopted clips) */
  clipBlobCache: new Map(),
  clipCacheFp: "",
  /** Playing stitched program.mp4 as a single file */
  usingProgramFile: false,
  programExporting: false,
  /** Clip file currently loaded (or loading) into the back buffer */
  preloadNextFile: null,
  _preloadToken: 0,
  history: {
    stack: [],
    index: -1,
    max: 40,
    applying: false,
  },
  /** last /api/health payload (clip_unit_seconds etc.) */
  health: null,
  taste: null,
};

function detectLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    const langs = (window.MFW_I18N && window.MFW_I18N.langs) || ["ja", "en", "zh"];
    if (saved && langs.includes(saved)) return saved;
  } catch (_) {}
  const nav = (navigator.language || "ja").toLowerCase();
  if (nav.startsWith("zh")) return "zh";
  if (nav.startsWith("en")) return "en";
  return "ja";
}

function t(key, vars) {
  const i18n = window.MFW_I18N;
  if (!i18n || !i18n.strings) {
    return key;
  }
  const pack = i18n.strings[state.lang] || i18n.strings.ja || {};
  const ja = i18n.strings.ja || {};
  let s = pack[key] ?? ja[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = String(s).split(`{${k}}`).join(String(v));
    }
  }
  return s;
}

function emotionLabel(jaKey) {
  const i18n = window.MFW_I18N;
  if (!i18n || !i18n.emotion) return jaKey;
  const map = i18n.emotion[jaKey];
  if (!map) return jaKey;
  return map[state.lang] || map.ja || jaKey;
}

function applyI18nStatic() {
  document.documentElement.lang =
    state.lang === "zh" ? "zh-CN" : state.lang === "en" ? "en" : "ja";
  document.title = t("docTitle");

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.setAttribute("placeholder", t(key));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.setAttribute("title", t(key));
  });

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === state.lang);
  });

  // rebuild project select placeholder + dynamic UI
  if (state.project) {
    refreshProjectList(state.project.id);
    renderGlobal();
    renderWave();
    renderSegments();
    updatePinUi();
  } else {
    refreshProjectList();
    updatePinUi();
  }
}

function setLang(lang) {
  const langs = (window.MFW_I18N && window.MFW_I18N.langs) || ["ja", "en", "zh"];
  if (!langs.includes(lang)) return;
  state.lang = lang;
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch (_) {}
  applyI18nStatic();
  renderSettingsProjects().catch(() => {});
  const st = $("status")?.textContent || "";
  if (!st || st.length < 80 || st.includes("undefined") || st.includes("MFW_I18N")) {
    setStatus(t("statusLang", { lang: langLabel(lang) }));
  }
}

function langLabel(code) {
  if (code === "en") return "English";
  if (code === "zh") return "中文";
  return "日本語";
}

function fmt(t) {
  if (!Number.isFinite(t)) return "0:00";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function cloneEditableSnapshot(project) {
  if (!project) return null;
  return JSON.parse(
    JSON.stringify({
      segments: project.segments || [],
      open_pin: project.open_pin ?? null,
      world: project.world || "",
      style: project.style || "",
      negative_prompt: project.negative_prompt || "",
      apply_taste: project.apply_taste !== false,
      lyrics: project.lyrics ?? "",
      bar_mode: project.bar_mode || "waveform",
      program: project.program ?? null,
    })
  );
}

function fillProjectMetaFields(p) {
  if (!p) return;
  if ($("world")) $("world").value = p.world || "";
  if ($("projStyle")) $("projStyle").value = p.style || "";
  if ($("projNegative")) $("projNegative").value = p.negative_prompt || "";
  if ($("applyTaste")) $("applyTaste").checked = p.apply_taste !== false;
  if ($("lyrics")) $("lyrics").value = p.lyrics || "";
}

function collectMetaBody(extra) {
  const barMode =
    document.querySelector('input[name="barMode"]:checked')?.value || "waveform";
  return {
    world: $("world") ? $("world").value : "",
    style: $("projStyle") ? $("projStyle").value : "",
    negative_prompt: $("projNegative") ? $("projNegative").value : "",
    apply_taste: $("applyTaste") ? !!$("applyTaste").checked : true,
    lyrics: $("lyrics") ? $("lyrics").value : "",
    bar_mode: barMode,
    ...(extra || {}),
  };
}

function estimateApiParts(seg) {
  const unit = Number(state.health?.clip_unit_seconds) || 5;
  const dur = Math.max(0, Number(seg?.t1) - Number(seg?.t0) || 0);
  if (dur <= 0) return 1;
  if (dur <= unit + 0.35) return 1;
  return Math.max(1, Math.ceil(dur / unit));
}

async function refreshTasteHints() {
  const line = $("tasteHintsLine");
  if (!line) return;
  try {
    const data = await api("/api/taste");
    state.taste = data;
    const hints = data.hints || [];
    if (!hints.length) {
      line.textContent = t("tasteHintsEmpty");
      return;
    }
    line.textContent = t("tasteHintsLabel") + " " + hints.slice(0, 3).join(" · ");
  } catch (_) {
    line.textContent = "";
  }
}

function genButtonLabel(seg) {
  const base = seg.video ? t("btnRegen") : t("btnGen");
  const n = estimateApiParts(seg);
  const unit = Number(state.health?.clip_unit_seconds) || 5;
  if (n <= 1) return `${base} · ~${unit}s×1`;
  return t("btnGenCost", { base, n, unit });
}

function resetHistory(project, label = "load") {
  const snap = cloneEditableSnapshot(project);
  state.history.stack = snap ? [{ snap, label, selectedSegId: state.selectedSegId }] : [];
  state.history.index = state.history.stack.length - 1;
  state.history.applying = false;
}

/** Call AFTER a successful mutating edit. Drops any redo branch. */
function commitHistory(label = "edit") {
  if (state.history.applying || !state.project) return;
  const snap = cloneEditableSnapshot(state.project);
  if (!snap) return;
  const tip = state.history.stack[state.history.index];
  if (tip && JSON.stringify(tip.snap) === JSON.stringify(snap)) return;
  state.history.stack = state.history.stack.slice(0, state.history.index + 1);
  state.history.stack.push({
    snap,
    label,
    selectedSegId: state.selectedSegId,
  });
  if (state.history.stack.length > state.history.max) {
    const drop = state.history.stack.length - state.history.max;
    state.history.stack.splice(0, drop);
  }
  state.history.index = state.history.stack.length - 1;
}

/** @deprecated alias — prefer commitHistory after edits */
function pushHistory(label = "edit") {
  commitHistory(label);
}

async function applyHistoryEntry(entry, verb) {
  if (!state.project || !entry?.snap) return;
  state.history.applying = true;
  try {
    const body = entry.snap;
    const restored = await api(`/api/projects/${state.project.id}/restore`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // keep non-editable fields from restored server project
    state.project = restored;
    state.selectedSegId = entry.selectedSegId || null;
    invalidateClipCache();
    prefetchAdoptedClips().catch(() => {});
    renderGlobal();
    renderWave();
    renderSegments();
    updatePinUi();
    applyBarMode(state.project.bar_mode || "waveform");
    fillProjectMetaFields(state.project);
    setStatus(
      verb === "undo"
        ? t("statusUndo", { label: entry.label || "" })
        : t("statusRedo", { label: entry.label || "" })
    );
  } catch (e) {
    setStatus(e.message);
  } finally {
    state.history.applying = false;
  }
}

async function undoEdit() {
  if (!state.project) return;
  if (state.history.index <= 0) {
    setStatus(t("statusNothingToUndo"));
    return;
  }
  state.history.index -= 1;
  const entry = state.history.stack[state.history.index];
  await applyHistoryEntry(entry, "undo");
}

async function redoEdit() {
  if (!state.project) return;
  if (state.history.index >= state.history.stack.length - 1) {
    setStatus(t("statusNothingToRedo"));
    return;
  }
  state.history.index += 1;
  const entry = state.history.stack[state.history.index];
  await applyHistoryEntry(entry, "redo");
}

function seekPlayheadToClientX(clientX) {
  if (!state.project?.digest) return null;
  const wrap = $("waveWrap");
  const rect = wrap.getBoundingClientRect();
  const x = clientX - rect.left;
  const ratio = Math.min(1, Math.max(0, x / Math.max(1, rect.width)));
  const tclick = xRatioToTime(ratio);
  const audio = $("audio");
  audio.currentTime = tclick;
  updatePlayhead();
  return tclick;
}


function openSettings(open) {
  const panel = $("settingsPanel");
  const back = $("settingsBackdrop");
  if (open) {
    panel.hidden = false;
    back.hidden = false;
    panel.classList.remove("hidden");
    back.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    // restore last drag position if any
    try {
      const raw = localStorage.getItem("mfw.settingsPos");
      if (raw) {
        const pos = JSON.parse(raw);
        if (typeof pos.left === "number" && typeof pos.top === "number") {
          panel.style.left = `${pos.left}px`;
          panel.style.top = `${pos.top}px`;
          panel.style.right = "auto";
        }
      }
    } catch (_) {}
    renderSettingsProjects().catch((e) => setStatus(e.message));
  } else {
    panel.classList.add("hidden");
    back.classList.add("hidden");
    panel.hidden = true;
    back.hidden = true;
    panel.setAttribute("aria-hidden", "true");
  }
}

function wireSettingsDrag() {
  const panel = $("settingsPanel");
  const head = panel && panel.querySelector(".settings-head");
  if (!panel || !head || head.dataset.dragWired) return;
  head.dataset.dragWired = "1";
  let dragging = false;
  let ox = 0;
  let oy = 0;

  const onMove = (ev) => {
    if (!dragging) return;
    const x = ev.clientX - ox;
    const y = ev.clientY - oy;
    const maxX = Math.max(8, window.innerWidth - panel.offsetWidth - 8);
    const maxY = Math.max(8, window.innerHeight - 48);
    const left = Math.min(maxX, Math.max(8, x));
    const top = Math.min(maxY, Math.max(8, y));
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.right = "auto";
  };
  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    try {
      localStorage.setItem(
        "mfw.settingsPos",
        JSON.stringify({
          left: parseFloat(panel.style.left) || 0,
          top: parseFloat(panel.style.top) || 0,
        })
      );
    } catch (_) {}
  };

  head.addEventListener("pointerdown", (ev) => {
    // don't start drag from close button
    if (ev.target.closest("button")) return;
    if (ev.button != null && ev.button !== 0) return;
    dragging = true;
    const rect = panel.getBoundingClientRect();
    ox = ev.clientX - rect.left;
    oy = ev.clientY - rect.top;
    panel.style.left = `${rect.left}px`;
    panel.style.top = `${rect.top}px`;
    panel.style.right = "auto";
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    ev.preventDefault();
  });
}

async function renderSettingsProjects() {
  const host = $("settingsProjectList");
  if (!host) return;
  host.textContent = "";
  let projects = [];
  try {
    const data = await api("/api/projects");
    projects = data.projects || [];
  } catch (e) {
    const err = document.createElement("p");
    err.className = "hint";
    err.textContent = e.message || String(e);
    host.appendChild(err);
    return;
  }
  const curId = state.project && state.project.id;
  for (const p of projects) {
    const row = document.createElement("div");
    row.className = "settings-proj-row" + (p.id === curId ? " is-current" : "");
    row.dataset.pid = p.id;

    const idLine = document.createElement("div");
    idLine.className = "proj-id";
    idLine.textContent =
      (p.id === curId ? `● ${t("projCurrent")} · ` : "") + (p.id || "");
    row.appendChild(idLine);

    const input = document.createElement("input");
    input.type = "text";
    input.value = p.title || p.id || "";
    input.maxLength = 200;
    input.setAttribute("aria-label", "project title");
    row.appendChild(input);

    const bRen = document.createElement("button");
    bRen.type = "button";
    bRen.className = "ghost";
    bRen.textContent = t("btnRename");
    bRen.onclick = () => renameProject(p.id, input.value).catch((e) => setStatus(t("statusRenameFail", { err: e.message })));
    row.appendChild(bRen);

    const bDel = document.createElement("button");
    bDel.type = "button";
    bDel.className = "ghost danger";
    bDel.textContent = t("btnDeleteProj");
    bDel.onclick = () =>
      deleteProjectUi(p.id, p.title || p.id).catch((e) =>
        setStatus(t("statusDeleteFail", { err: e.message }))
      );
    row.appendChild(bDel);

    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        bRen.click();
      }
    });

    host.appendChild(row);
  }
  if (!projects.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "—";
    host.appendChild(empty);
  }
}

async function openCurrentProjectFolder() {
  if (!state.project || !state.project.id) {
    throw new Error(t("statusImportFirst") || "no project");
  }
  const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/reveal`, {
    method: "POST",
  });
  setStatus(t("statusOpenFolder") + (data.path ? ` · ${data.path}` : ""));
}

async function renameProject(pid, title) {
  const name = String(title || "").trim();
  if (!name) throw new Error("empty title");
  const p = await api(`/api/projects/${encodeURIComponent(pid)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: name }),
  });
  if (state.project && state.project.id === pid) {
    state.project.title = p.title;
  }
  await refreshProjectList(state.project ? state.project.id : pid);
  await renderSettingsProjects();
  setStatus(t("statusRenamed", { title: p.title || name }));
}

async function deleteProjectUi(pid, title) {
  const msg = t("confirmDeleteProj", { title: title || pid });
  if (!window.confirm(msg)) return;
  const wasCurrent = state.project && state.project.id === pid;
  await api(`/api/projects/${encodeURIComponent(pid)}`, { method: "DELETE" });
  // clear local undo for deleted project
  if (wasCurrent) {
    state.project = null;
    state.history = { stack: [], index: -1, applying: false, max: 50 };
    try {
      invalidateClipCache();
    } catch (_) {}
  }
  await refreshProjectList();
  const data = await api("/api/projects");
  const rest = data.projects || [];
  if (rest.length) {
    const next = rest[0];
    await loadProject(next.id);
    const sel = $("projectSelect");
    if (sel) sel.value = next.id;
  } else {
    await createProject();
  }
  await renderSettingsProjects();
  setStatus(t("statusDeleted"));
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch (_) {
      try {
        detail = await res.text();
      } catch (__) {}
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res;
}

async function refreshProjectList(selectId) {
  const data = await api("/api/projects");
  const sel = $("projectSelect");
  if (!sel) return data;
  const prefer =
    selectId ||
    (state.project && state.project.id) ||
    sel.value ||
    (() => {
      try {
        return localStorage.getItem("mfw.projectId") || "";
      } catch (_) {
        return "";
      }
    })();
  sel.textContent = "";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = t("projectPlaceholder") || "—";
  sel.appendChild(opt0);
  const projects = data.projects || [];
  for (const p of projects) {
    const o = document.createElement("option");
    o.value = p.id;
    const title = (p.title || "").trim() || p.id;
    o.textContent = title;
    o.title = `${title} (${p.id})`;
    sel.appendChild(o);
  }
  if (prefer && projects.some((p) => p.id === prefer)) {
    sel.value = prefer;
  } else if (projects.length) {
    sel.value = projects[0].id;
  } else {
    sel.value = "";
  }
  return data;
}

async function createProject() {
  const fd = new FormData();
  fd.append("title", "Untitled");
  const p = await api("/api/projects", { method: "POST", body: fd });
  await loadProject(p.id);
  await refreshProjectList(p.id);
  setStatus(t("statusNew"));
}

async function loadProject(id) {
  const p = await api(`/api/projects/${id}`);
  state.project = p;
  try {
    localStorage.setItem("mfw.projectId", id);
  } catch (_) {}
  const sel = $("projectSelect");
  if (sel && sel.value !== id) {
    // ensure option exists
    if (![...sel.options].some((o) => o.value === id)) {
      await refreshProjectList(id);
    } else {
      sel.value = id;
    }
  }
  state.lastPinTime = p.open_pin;
  if (state.lastPinTime == null && p.segments?.length) {
    state.lastPinTime = p.segments[p.segments.length - 1].t1;
  }
  resetViewFull();
  fillProjectMetaFields(p);
  const mode = p.bar_mode || "waveform";
  for (const r of document.querySelectorAll('input[name="barMode"]')) {
    r.checked = r.value === mode;
  }
  applyBarMode(mode);
  bindAudio(p.id, p.source_audio);
  clearVideoLayers();
  invalidateClipCache();
  renderGlobal();
  renderWave();
  renderSegments();
  updatePinUi();
  resetHistory(state.project, "load");
  setStatus(
    p.digest ? t("statusDigested", { id: p.digest.theory_id }) : t("statusNoImport")
  );
  prefetchAdoptedClips().catch(() => {});
  refreshTasteHints().catch(() => {});
}

function bindAudio(pid, hasSource) {
  const audio = $("audio");
  if (state.audioUrl) URL.revokeObjectURL(state.audioUrl);
  if (!hasSource) {
    audio.removeAttribute("src");
    audio.load();
    return;
  }
  audio.src = `/api/projects/${pid}/audio?t=${Date.now()}`;
  audio.load();
}

async function importFile(file) {
  if (!state.project) await createProject();
  const pid = state.project.id;
  setStatus(t("statusImporting"));
  const fd = new FormData();
  fd.append("file", file);
  const p = await api(`/api/projects/${pid}/import`, { method: "POST", body: fd });
  state.project = p;
  state.lastPinTime = null;
  resetViewFull();
  bindAudio(pid, true);
  renderGlobal();
  renderWave();
  renderSegments();
  await refreshProjectList(pid);
  setStatus(
    t("statusImported", {
      bpm: p.digest.global.tempo_bpm,
      sec: p.digest.global.duration_sec,
    })
  );
}

function applyBarMode(mode) {
  const wave = $("waveWrap");
  const lyr = $("lyricsBox");
  if (mode === "waveform") {
    wave.classList.remove("hidden");
    lyr.classList.add("hidden");
  } else if (mode === "lyrics") {
    wave.classList.add("hidden");
    lyr.classList.remove("hidden");
  } else {
    wave.classList.remove("hidden");
    lyr.classList.remove("hidden");
  }
}

function renderGlobal() {
  const box = $("globalFeat");
  box.textContent = "";
  const g = state.project?.digest?.global;
  if (!g) return;
  const entries = [
    ["tempo", `${g.tempo_bpm} BPM`],
    ["centroid", `${g.spectral_centroid_mean_hz} Hz`],
    ["low/high", g.low_high_ratio],
    ["onset", g.onset_density],
    ["RMS", g.rms_mean],
  ];
  for (const [k, v] of entries) {
    const s = document.createElement("span");
    s.className = "chip";
    s.textContent = `${k}: ${v}`;
    box.appendChild(s);
  }
}

function duration() {
  return Number(state.project?.digest?.global?.duration_sec || $("audio").duration || 0);
}

function ensureView() {
  const dur = duration();
  if (!(dur > 0)) {
    state.viewStart = 0;
    state.viewEnd = null;
    return { start: 0, end: 1, span: 1, dur: 0 };
  }
  let start = Number(state.viewStart) || 0;
  let end = state.viewEnd == null ? dur : Number(state.viewEnd);
  if (!Number.isFinite(end) || end <= start) end = dur;
  start = Math.max(0, Math.min(start, dur));
  end = Math.max(start + 0.05, Math.min(end, dur));
  // minimum window ~0.25s for precision pinning
  const minSpan = Math.min(0.25, dur);
  if (end - start < minSpan) {
    end = Math.min(dur, start + minSpan);
    start = Math.max(0, end - minSpan);
  }
  state.viewStart = start;
  state.viewEnd = end;
  return { start, end, span: end - start, dur };
}

function resetViewFull() {
  const dur = duration();
  state.viewStart = 0;
  state.viewEnd = dur > 0 ? dur : null;
}

function timeToXRatio(t) {
  const v = ensureView();
  if (v.span <= 0) return 0;
  return (t - v.start) / v.span;
}

function xRatioToTime(ratio) {
  const v = ensureView();
  return v.start + Math.min(1, Math.max(0, ratio)) * v.span;
}

function isTypingTarget(el) {
  if (!el || el === document.body) return false;
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (el.isContentEditable) return true;
  return !!el.closest?.("textarea, input, select, [contenteditable='true']");
}

function togglePlay() {
  const a = $("audio");
  applyPlayRate(state.playRate);
  if ($("syncMusic")?.checked) {
    state.syncMusic = true;
    state.previewMode = "program";
  }
  if (!a.src && !state.project?.source_audio) return;
  if (a.paused) {
    a.play().catch(() => {});
    cancelAnimationFrame(state.raf);
    state.raf = requestAnimationFrame(tick);
  } else {
    a.pause();
    cancelAnimationFrame(state.raf);
  }
}

function seekToStart() {
  const a = $("audio");
  a.currentTime = 0;
  updatePlayhead();
  // keep play state
}

/** Current frame start: open pin, else selected segment t0, else segment under playhead, else last segment t0. */
function currentFrameStart() {
  if (state.project?.open_pin != null) return Number(state.project.open_pin);
  const segs = state.project?.segments || [];
  if (state.selectedSegId) {
    const sel = segs.find((s) => s.id === state.selectedSegId);
    if (sel) return Number(sel.t0);
  }
  const t = $("audio").currentTime || 0;
  const under = segmentAtTime(t);
  if (under) return Number(under.t0);
  if (segs.length) return Number(segs[segs.length - 1].t0);
  return 0;
}

function segmentAtTime(t) {
  const segs = state.project?.segments || [];
  // prefer tightest / last matching if overlap
  let hit = null;
  for (const s of segs) {
    if (t >= s.t0 - 1e-4 && t <= s.t1 + 1e-4) hit = s;
  }
  return hit;
}

function ensurePlayheadInView(t) {
  const dur = duration();
  const v = ensureView();
  if (t >= v.start && t <= v.end) return;
  const span = v.span;
  let ns = t - span * 0.3;
  let ne = ns + span;
  if (ns < 0) {
    ns = 0;
    ne = Math.min(dur, span);
  }
  if (ne > dur) {
    ne = dur;
    ns = Math.max(0, dur - span);
  }
  state.viewStart = ns;
  state.viewEnd = ne;
  renderWave();
}

function playFromFrameStart() {
  const a = $("audio");
  const t0 = currentFrameStart();
  const dur = duration();
  a.currentTime = Math.max(0, Math.min(t0, dur > 0 ? dur - 0.01 : t0));
  updatePlayhead();
  ensurePlayheadInView(a.currentTime);
  a.play().catch(() => {});
  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
}

function selectSegment(sid, { focusPrompt = true } = {}) {
  state.selectedSegId = sid;
  renderWave();
  renderSegments();
  const el = document.querySelector(`.seg-card[data-id="${sid}"]`);
  el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  if (focusPrompt) {
    const ta = el?.querySelector("textarea");
    if (ta) {
      // focus without stealing if user is mid-shortcut chain — call after M closes etc.
      requestAnimationFrame(() => {
        ta.focus({ preventScroll: true });
        const len = ta.value.length;
        try {
          ta.setSelectionRange(len, len);
        } catch (_) {}
      });
    }
  }
}

async function placePinAtPlayhead() {
  if (!state.project?.digest) {
    setStatus(t("statusImportFirst"));
    return;
  }
  const a = $("audio");
  const tclick = Number(a.currentTime) || 0;
  state.lastPinTime = tclick;
  try {
    const data = await api(`/api/projects/${state.project.id}/pin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ t: tclick }),
    });
    state.project = data.project;
    if (data.status === "closed" && data.segment) {
      state.lastPinTime = data.segment.t1;
      state.selectedSegId = data.segment.id;
      updatePinUi();
      renderWave();
      renderSegments();
      commitHistory("pin");
      setStatus(
        t("statusSegClosed", {
          a: fmt(data.segment.t0),
          b: fmt(data.segment.t1),
        })
      );
      selectSegment(data.segment.id, { focusPrompt: true });
    } else {
      if (data.open_pin != null) state.lastPinTime = data.open_pin;
      updatePinUi();
      renderWave();
      commitHistory("pin");
      setStatus(t("statusPinOpen", { t: fmt(data.open_pin) }));
    }
  } catch (e) {
    setStatus(t("statusPinFail", { err: e.message }));
  }
}

function nudgeSeek(delta) {
  const a = $("audio");
  const dur = duration() || a.duration || 0;
  a.currentTime = Math.max(0, Math.min(dur, (a.currentTime || 0) + delta));
  updatePlayhead();
  ensurePlayheadInView(a.currentTime);
}

function zoomBy(factor, anchorRatio = 0.5) {
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0)) return;
  const anchor = v.start + v.span * anchorRatio;
  let span = v.span * factor;
  const minSpan = Math.min(0.25, dur);
  span = Math.max(minSpan, Math.min(dur, span));
  let ns = anchor - span * anchorRatio;
  let ne = ns + span;
  if (ns < 0) {
    ns = 0;
    ne = span;
  }
  if (ne > dur) {
    ne = dur;
    ns = Math.max(0, dur - span);
  }
  state.viewStart = ns;
  state.viewEnd = ne;
  renderWave();
}


function selectedSegment() {
  if (!state.selectedSegId) return null;
  return (state.project?.segments || []).find((s) => s.id === state.selectedSegId) || null;
}

function toggleLoopSelected() {
  const seg = selectedSegment();
  if (!seg) {
    setStatus(t("statusNeedSeg"));
    return;
  }
  if (state.loopSegId === seg.id) {
    state.loopSegId = null;
    setStatus(t("statusLoopOff"));
    return;
  }
  state.loopSegId = seg.id;
  const a = $("audio");
  a.currentTime = seg.t0;
  ensurePlayheadInView(seg.t0);
  a.play().catch(() => {});
  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
  setStatus(t("statusLoopOn", { a: fmt(seg.t0), b: fmt(seg.t1) }));
}

function zoomFitSelected() {
  const seg = selectedSegment();
  if (!seg) {
    setStatus(t("statusNeedSeg"));
    return;
  }
  const dur = duration();
  const pad = Math.max(0.15, (seg.t1 - seg.t0) * 0.15);
  let ns = Math.max(0, seg.t0 - pad);
  let ne = Math.min(dur, seg.t1 + pad);
  if (ne - ns < 0.25) {
    const mid = (seg.t0 + seg.t1) / 2;
    ns = Math.max(0, mid - 0.125);
    ne = Math.min(dur, ns + 0.25);
  }
  state.viewStart = ns;
  state.viewEnd = ne;
  renderWave();
  setStatus(t("statusZoomFit", { a: fmt(seg.t0), b: fmt(seg.t1) }));
}

function selectSegmentByDelta(delta) {
  const segs = state.project?.segments || [];
  if (!segs.length) {
    setStatus(t("statusNeedSeg"));
    return;
  }
  let idx = segs.findIndex((s) => s.id === state.selectedSegId);
  if (idx < 0) idx = delta > 0 ? -1 : 0;
  idx = (idx + delta + segs.length) % segs.length;
  selectSegment(segs[idx].id, { focusPrompt: false });
  const a = $("audio");
  a.currentTime = segs[idx].t0;
  ensurePlayheadInView(segs[idx].t0);
  updatePlayhead();
  setStatus(t("statusSegSelected", { a: fmt(segs[idx].t0), b: fmt(segs[idx].t1) }));
}



async function deleteSelectedSegment() {
  if (!state.project || !state.selectedSegId) return;
  const sid = state.selectedSegId;
  state.project = await api(`/api/projects/${state.project.id}/segments/${sid}`, {
    method: "DELETE",
  });
  state.selectedSegId = null;
  renderWave();
  renderSegments();
  commitHistory("delete-seg");
  setStatus(t("statusSegDeleted"));
}

function panViewBy(deltaSec) {
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0) || Math.abs(v.span - dur) < 0.02) return false;
  let ns = v.start + deltaSec;
  let ne = v.end + deltaSec;
  if (ns < 0) {
    ne -= ns;
    ns = 0;
  }
  if (ne > dur) {
    ns -= ne - dur;
    ne = dur;
  }
  ns = Math.max(0, ns);
  ne = Math.min(dur, ne);
  state.viewStart = ns;
  state.viewEnd = ne;
  renderWave();
  updateZoomLabel();
  syncWaveScroll();
  return true;
}

function onWaveWheel(ev) {
  if (!state.project?.digest) return;
  const wrap = $("waveWrap");
  const rect = wrap.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const ratio = Math.min(1, Math.max(0, x / Math.max(1, rect.width)));
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0)) return;

  const absX = Math.abs(ev.deltaX || 0);
  const absY = Math.abs(ev.deltaY || 0);
  // Horizontal roll / trackpad sideways / Shift+wheel = pan the window
  const wantPan = ev.shiftKey || absX > absY + 0.5 || (ev.deltaX && absX >= absY);
  if (wantPan) {
    ev.preventDefault();
    const raw = absX >= absY ? ev.deltaX : ev.deltaY;
    // pixel / line / page modes
    let scale = 0.0018;
    if (ev.deltaMode === 1) scale = 0.08; // lines
    if (ev.deltaMode === 2) scale = 0.35; // pages
    panViewBy(raw * scale * v.span);
    return;
  }

  ev.preventDefault();
  const anchor = xRatioToTime(ratio);
  const factor = ev.deltaY < 0 ? 0.82 : 1.22;
  let span = v.span * factor;
  const minSpan = Math.min(0.25, dur);
  const maxSpan = dur;
  span = Math.max(minSpan, Math.min(maxSpan, span));
  let ns = anchor - span * ratio;
  let ne = ns + span;
  if (ns < 0) {
    ns = 0;
    ne = span;
  }
  if (ne > dur) {
    ne = dur;
    ns = Math.max(0, dur - span);
  }
  state.viewStart = ns;
  state.viewEnd = ne;
  renderWave();
  updateZoomLabel();
  syncWaveScroll();
}

function syncWaveScroll() {
  if (state._scrollDragging || state._scrollSync) return;
  const row = $("waveScrollRow");
  const el = $("waveScroll");
  if (!row || !el) return;
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0)) {
    row.hidden = true;
    el.disabled = true;
    return;
  }
  // Show bar whenever we can pan (zoomed in). Keep visible but disabled at full zoom.
  const full = v.span >= dur - 0.02;
  row.hidden = false;
  el.disabled = full;
  if (full) {
    state._scrollSync = true;
    el.value = "0";
    state._scrollSync = false;
    return;
  }
  const travel = Math.max(1e-6, dur - v.span);
  const max = 1000;
  el.min = "0";
  el.max = String(max);
  el.step = "1";
  const ratio = Math.min(1, Math.max(0, (v.start - 0) / travel));
  state._scrollSync = true;
  el.value = String(Math.round(ratio * max));
  state._scrollSync = false;
}

function onWaveScrollInput(ev) {
  if (state._scrollSync) return;
  const el = $("waveScroll");
  if (!el || el.disabled) return;
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0)) return;

  // If somehow still full-window, open a zoomed window then pan
  let span = v.span;
  if (span >= dur - 0.02) {
    span = Math.max(Math.min(dur * 0.35, dur), Math.min(8, dur));
  }
  const travel = Math.max(1e-6, dur - span);
  const max = Number(el.max) || 1000;
  const start = (Number(el.value) / max) * travel;

  state._scrollDragging = true;
  state.viewStart = Math.max(0, Math.min(start, travel));
  state.viewEnd = Math.min(dur, state.viewStart + span);
  // keep span exact
  if (state.viewEnd - state.viewStart < span - 1e-6) {
    state.viewStart = Math.max(0, state.viewEnd - span);
  }
  renderWave();
  updateZoomLabel();
  updatePlayhead();
  state._scrollDragging = false;
  // mirror thumb without fighting the drag
  state._scrollSync = true;
  const travel2 = Math.max(1e-6, dur - (state.viewEnd - state.viewStart));
  el.value = String(
    Math.round(((state.viewStart - 0) / travel2) * (Number(el.max) || 1000))
  );
  state._scrollSync = false;
}

function updateZoomLabel() {
  const el = $("zoomLabel");
  if (!el) return;
  const v = ensureView();
  const dur = v.dur;
  if (!(dur > 0)) {
    el.textContent = "";
    return;
  }
  const full = Math.abs(v.span - dur) < 0.02;
  if (full) {
    el.textContent = t("zoomFull");
  } else {
    el.textContent = t("zoomWindow", {
      a: fmt(v.start),
      b: fmt(v.end),
      z: (dur / v.span).toFixed(1),
    });
  }
}

function renderWave() {
  const canvas = $("wave");
  const wrap = $("waveWrap");
  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(100, wrap.clientWidth || 600);
  const cssH = Math.max(160, wrap.clientHeight || 280);
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = "#080a0e";
  ctx.fillRect(0, 0, cssW, cssH);

  const v = ensureView();
  const peaks = state.project?.digest?.waveform_peaks || [];
  if (!peaks.length) {
    ctx.fillStyle = "#556";
    ctx.font = "14px system-ui";
    ctx.fillText(t("featWaveEmpty"), 16, cssH / 2);
  } else {
    const mid = cssH / 2;
    const dur = v.dur || 1;
    // map peak index i -> time = i/(n-1)*dur
    const n = peaks.length;
    const i0 = Math.max(0, Math.floor(((v.start / dur) * (n - 1))));
    const i1 = Math.min(n - 1, Math.ceil(((v.end / dur) * (n - 1))));
    ctx.strokeStyle = "#7eb6d6";
    ctx.lineWidth = 1;
    ctx.beginPath();
    const count = Math.max(1, i1 - i0);
    for (let k = 0; k <= count; k++) {
      const i = i0 + k;
      const tSec = (i / (n - 1 || 1)) * dur;
      const x = timeToXRatio(tSec) * cssW;
      const h = peaks[i] * (cssH * 0.45);
      ctx.moveTo(x, mid - h);
      ctx.lineTo(x, mid + h);
    }
    ctx.stroke();

    // second ticks when zoomed enough (< 30s window)
    if (v.span <= 30) {
      ctx.fillStyle = "rgba(255,255,255,0.12)";
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      const step = v.span <= 5 ? 0.5 : v.span <= 15 ? 1 : 2;
      const first = Math.ceil(v.start / step) * step;
      ctx.font = "10px system-ui";
      ctx.fillStyle = "rgba(180,190,200,0.55)";
      for (let t = first; t <= v.end + 1e-6; t += step) {
        const x = timeToXRatio(t) * cssW;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, cssH);
        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.stroke();
        ctx.fillText(fmt(t), x + 3, 12);
      }
    }
  }

  const layer = $("segmentsLayer");
  layer.textContent = "";
  for (const s of state.project?.segments || []) {
    const r0 = timeToXRatio(s.t0);
    const r1 = timeToXRatio(s.t1);
    if (r1 < 0 || r0 > 1) continue;
    const left = Math.max(0, r0) * 100;
    const right = Math.min(1, r1) * 100;
    const el = document.createElement("div");
    el.className = "seg-band" + (state.selectedSegId === s.id ? " selected" : "");
    el.style.left = left + "%";
    el.style.width = Math.max(0.15, right - left) + "%";
    el.title = `${fmt(s.t0)} – ${fmt(s.t1)}`;
    el.dataset.sid = s.id;
    const hl = document.createElement("div");
    hl.className = "seg-handle left";
    hl.dataset.edge = "left";
    const hr = document.createElement("div");
    hr.className = "seg-handle right";
    hr.dataset.edge = "right";
    el.appendChild(hl);
    el.appendChild(hr);
    const startDrag = (edge) => (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      state.drag = {
        sid: s.id,
        edge,
        t0: s.t0,
        t1: s.t1,
        moved: false,
      };
      el.classList.add("dragging");
      state.selectedSegId = s.id;
    };
    const onHandleDown = (edge) => (ev) => {
      // double-click should seek, not start resize
      if (ev.detail >= 2) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      startDrag(edge)(ev);
    };
    hl.addEventListener("pointerdown", onHandleDown("left"));
    hr.addEventListener("pointerdown", onHandleDown("right"));
    el.addEventListener("pointerdown", (ev) => {
      if (ev.target.classList.contains("seg-handle")) return;
      if (ev.button !== 0) return;
      // double-click = playhead seek inside the band (do not start move-drag)
      if (ev.detail >= 2) {
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      ev.preventDefault();
      ev.stopPropagation();
      state.drag = {
        sid: s.id,
        edge: "move",
        t0: s.t0,
        t1: s.t1,
        originX: ev.clientX,
        originT0: s.t0,
        originT1: s.t1,
        moved: false,
      };
      el.classList.add("dragging");
      state.selectedSegId = s.id;
    });
    el.addEventListener("dblclick", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      state._suppressClick = true;
      state.drag = null;
      el.classList.remove("dragging");
      if (ev.altKey) {
        resetViewFull();
        renderWave();
        syncWaveScroll();
        setStatus(t("statusZoomReset"));
        return;
      }
      const tt = seekPlayheadToClientX(ev.clientX);
      state.selectedSegId = s.id;
      renderWave();
      renderSegments();
      if (tt != null) {
        setStatus(t("statusSeekInSeg", { t: fmt(tt), a: fmt(s.t0), b: fmt(s.t1) }));
      }
    });
    layer.appendChild(el);
  }

  const open = state.project?.open_pin;
  const mark = $("openPinMark");
  if (open != null && v.dur > 0) {
    const r = timeToXRatio(open);
    if (r >= 0 && r <= 1) {
      mark.classList.remove("hidden");
      mark.style.left = r * 100 + "%";
    } else {
      mark.classList.add("hidden");
    }
  } else {
    mark.classList.add("hidden");
  }
  updatePlayhead();
  updateZoomLabel();
  syncWaveScroll();
}

function updatePlayhead() {
  const audio = $("audio");
  const dur = duration() || audio.duration || 0;
  let tcur = audio.currentTime || 0;
  if (state.loopSegId && !audio.paused) {
    const seg = (state.project?.segments || []).find((s) => s.id === state.loopSegId);
    if (seg && tcur >= seg.t1 - 0.02) {
      audio.currentTime = seg.t0;
      tcur = seg.t0;
    }
  }
  const r = timeToXRatio(tcur);
  const ph = $("playhead");
  if (r < 0 || r > 1) {
    ph.style.opacity = "0.25";
    ph.style.left = (r < 0 ? 0 : 100) + "%";
  } else {
    ph.style.opacity = "1";
    ph.style.left = r * 100 + "%";
  }
  const v = ensureView();
  const zoomBit =
    dur > 0 && v.span < dur - 0.02 ? ` · ${fmt(v.start)}–${fmt(v.end)}` : "";
  $("timeLabel").textContent = `${fmt(tcur)} / ${fmt(dur)}${zoomBit}`;
  syncVideoToMusic();
}

function tick() {
  updatePlayhead();
  state.raf = requestAnimationFrame(tick);
}

function updatePinUi() {
  const open = state.project?.open_pin;
  $("pinState").textContent =
    open == null ? t("pinNone") : t("pinOpen", { t: fmt(open) });
}

function renderSegments() {
  const root = $("segments");
  root.textContent = "";
  const segs = state.project?.segments || [];
  if (!segs.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = t("emptySegs");
    root.appendChild(empty);
    return;
  }
  for (const s of [...segs].reverse()) {
    const card = document.createElement("div");
    card.className = "seg-card" + (state.selectedSegId === s.id ? " active" : "");
    card.dataset.id = s.id;

    const head = document.createElement("div");
    head.className = "seg-head";
    const title = document.createElement("strong");
    title.textContent = t("segLabel");
    const time = document.createElement("time");
    time.textContent = `${fmt(s.t0)} – ${fmt(s.t1)} · ${(s.t1 - s.t0).toFixed(2)}s`;
    head.appendChild(title);
    head.appendChild(time);
    card.appendChild(head);

    const kwRow = document.createElement("div");
    kwRow.className = "kw-row";
    const lab = document.createElement("span");
    lab.className = "mini";
    lab.textContent = t("aiEmotion") + ":";
    kwRow.appendChild(lab);
    for (const k of s.emotion_keywords || []) {
      const sp = document.createElement("span");
      sp.className = "kw";
      sp.textContent = emotionLabel(k);
      kwRow.appendChild(sp);
    }
    if (s.unmatched) {
      const u = document.createElement("span");
      u.className = "chip warn";
      u.textContent = t("unmatched");
      kwRow.appendChild(u);
    }
    card.appendChild(kwRow);

    if (s.constraints?.soft_tags?.length) {
      const bias = document.createElement("div");
      bias.className = "mini";
      bias.textContent = t("bias") + ": " + s.constraints.soft_tags.join(", ");
      card.appendChild(bias);
    }

    const ta = document.createElement("textarea");
    ta.rows = 3;
    ta.placeholder = t("promptPh");
    ta.value = s.prompt || "";
    ta.addEventListener("change", async () => {
      try {
        await api(`/api/projects/${state.project.id}/segments/${s.id}/prompt`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: ta.value }),
        });
        s.prompt = ta.value;
        commitHistory("prompt");
        setStatus(t("statusPromptSaved"));
      } catch (e) {
        setStatus(t("statusPromptFail", { err: e.message }));
      }
    });
    card.appendChild(ta);

    // Segment craft mode: hold | shift | motion
    const modeRow = document.createElement("div");
    modeRow.className = "mode-row";
    const modeLab = document.createElement("span");
    modeLab.className = "mini";
    modeLab.textContent = t("segMode") + ":";
    modeRow.appendChild(modeLab);
    const modeSel = document.createElement("select");
    modeSel.className = "mode-select";
    for (const m of ["hold", "shift", "motion"]) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = t("mode_" + m);
      modeSel.appendChild(opt);
    }
    modeSel.value = s.mode || "hold";
    modeSel.addEventListener("change", async () => {
      const mode = modeSel.value;
      try {
        const data = await api(`/api/projects/${state.project.id}/segments/${s.id}/mode`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }),
        });
        const seg = (state.project.segments || []).find((x) => x.id === s.id);
        if (seg && data) Object.assign(seg, data);
        commitHistory("mode");
        setStatus(t("statusModeSet", { mode: t("mode_" + (data.mode || mode)) }));
        renderSegments();
      } catch (e) {
        modeSel.value = s.mode || "hold";
        setStatus(t("statusModeFail", { err: e.message }));
      }
    });
    modeRow.appendChild(modeSel);
    const modeHint = document.createElement("span");
    modeHint.className = "hint mode-hint";
    modeHint.textContent = t("modeHint_" + (modeSel.value || "hold"));
    modeSel.addEventListener("input", () => {
      modeHint.textContent = t("modeHint_" + modeSel.value);
    });
    modeRow.appendChild(modeHint);
    card.appendChild(modeRow);

    // Reference image for i2v generate
    const refRow = document.createElement("div");
    refRow.className = "ref-row";
    const refLab = document.createElement("span");
    refLab.className = "ref-label";
    refLab.textContent = t("refImage");
    refRow.appendChild(refLab);

    const refThumb = document.createElement("img");
    refThumb.className = "ref-thumb" + (s.ref_image ? "" : " hidden");
    refThumb.alt = "";
    if (s.ref_image) {
      refThumb.src = `/api/projects/${state.project.id}/refs/${encodeURIComponent(s.ref_image)}?t=${Date.now()}`;
    }
    refRow.appendChild(refThumb);

    const refName = document.createElement("span");
    refName.className = "ref-name hint";
    refName.textContent = s.ref_image ? s.ref_image : t("refImageNone");
    refRow.appendChild(refName);

    const refFile = document.createElement("input");
    refFile.type = "file";
    refFile.accept = "image/*,.jpg,.jpeg,.png,.webp,.gif";
    refFile.hidden = true;
    refFile.addEventListener("change", async () => {
      const f = refFile.files && refFile.files[0];
      refFile.value = "";
      if (!f) return;
      try {
        const fd = new FormData();
        fd.append("file", f, f.name || "ref.jpg");
        const data = await api(
          `/api/projects/${state.project.id}/segments/${s.id}/ref-image`,
          { method: "POST", body: fd }
        );
        const seg = (state.project.segments || []).find((x) => x.id === s.id);
        if (seg && data.segment) Object.assign(seg, data.segment);
        else if (seg) seg.ref_image = data.ref_image;
        commitHistory("ref-image");
        renderSegments();
        setStatus(t("statusRefOk"));
      } catch (e) {
        setStatus(t("statusRefFail", { err: e.message }));
      }
    });
    refRow.appendChild(refFile);

    const bRef = document.createElement("button");
    bRef.type = "button";
    bRef.className = "ghost";
    bRef.textContent = t("btnRefImage");
    bRef.onclick = (ev) => {
      ev.preventDefault();
      refFile.click();
    };
    refRow.appendChild(bRef);

    const bRefClear = document.createElement("button");
    bRefClear.type = "button";
    bRefClear.className = "ghost";
    bRefClear.textContent = t("btnRefClear");
    bRefClear.disabled = !s.ref_image;
    bRefClear.onclick = async (ev) => {
      ev.preventDefault();
      try {
        const data = await api(
          `/api/projects/${state.project.id}/segments/${s.id}/ref-image`,
          { method: "DELETE" }
        );
        const seg = (state.project.segments || []).find((x) => x.id === s.id);
        if (seg && data.segment) Object.assign(seg, data.segment);
        else if (seg) seg.ref_image = null;
        commitHistory("ref-clear");
        renderSegments();
        setStatus(t("statusRefCleared"));
      } catch (e) {
        setStatus(t("statusRefFail", { err: e.message }));
      }
    };
    refRow.appendChild(bRefClear);
    card.appendChild(refRow);

    // Camera lock toggle (hard tripod lock in composed prompt)
    const lockRow = document.createElement("label");
    lockRow.className = "camera-lock-label";
    const lockCb = document.createElement("input");
    lockCb.type = "checkbox";
    lockCb.checked = !!s.camera_lock;
    lockCb.addEventListener("change", async () => {
      const on = !!lockCb.checked;
      try {
        const data = await api(
          `/api/projects/${state.project.id}/segments/${s.id}/camera-lock`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ camera_lock: on }),
          }
        );
        const seg = (state.project.segments || []).find((x) => x.id === s.id);
        if (seg) {
          seg.camera_lock = !!(data && data.camera_lock);
        }
        commitHistory("camera-lock");
        setStatus(on ? t("statusCameraLockOn") : t("statusCameraLockOff"));
        renderSegments();
      } catch (e) {
        lockCb.checked = !!s.camera_lock;
        setStatus(t("statusCameraLockFail", { err: e.message }));
      }
    });
    lockRow.appendChild(lockCb);
    const lockTxt = document.createElement("span");
    lockTxt.textContent = t("cameraLock");
    lockRow.appendChild(lockTxt);
    card.appendChild(lockRow);

    const actions = document.createElement("div");
    actions.className = "seg-actions";

    const bGen = document.createElement("button");
    bGen.type = "button";
    bGen.className = "primary";
    bGen.textContent = genButtonLabel(s);
    bGen.title = t("btnGenCostHint", {
      n: estimateApiParts(s),
      unit: Number(state.health?.clip_unit_seconds) || 5,
    });
    bGen.disabled = state.genInflight.has(s.id);
    bGen.onclick = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      generateSeg(s.id, ta.value);
    };
    actions.appendChild(bGen);

    const bUn = document.createElement("button");
    bUn.type = "button";
    bUn.textContent = t("btnUnmatch");
    bUn.onclick = () => unmatchSeg(s.id);
    actions.appendChild(bUn);

    const bShow = document.createElement("button");
    bShow.type = "button";
    bShow.className = "ghost";
    bShow.textContent = t("btnShow");
    const hasClip = !!(activeClip(s)?.file);
    bShow.disabled = !hasClip;
    bShow.onclick = () => showVideo(s);
    actions.appendChild(bShow);

    const bPlayMus = document.createElement("button");
    bPlayMus.type = "button";
    bPlayMus.className = "ghost";
    bPlayMus.textContent = t("btnPlayWithMusic");
    bPlayMus.disabled = !hasClip;
    bPlayMus.onclick = () => playSegmentWithMusic(s);
    actions.appendChild(bPlayMus);

    const bDel = document.createElement("button");
    bDel.type = "button";
    bDel.className = "danger ghost";
    bDel.textContent = t("btnDel");
    bDel.onclick = async () => {
      state.project = await api(
        `/api/projects/${state.project.id}/segments/${s.id}`,
        { method: "DELETE" }
      );
      if (state.selectedSegId === s.id) state.selectedSegId = null;
      if (state.previewSegId === s.id) {
        clearVideoLayers();
      }
      invalidateClipCache();
      prefetchAdoptedClips().catch(() => {});
      renderWave();
      renderSegments();
    };
    actions.appendChild(bDel);

    card.appendChild(actions);

    // Materials / candidate clips
    const mats = document.createElement("div");
    mats.className = "materials";
    const mh = document.createElement("div");
    mh.className = "materials-h";
    mh.textContent = t("materials");
    mats.appendChild(mh);
    const list = document.createElement("div");
    list.className = "clip-list";
    const clips = s.clips || [];
    if (!clips.length) {
      const empty = document.createElement("div");
      empty.className = "mini";
      empty.textContent = t("materialsEmpty");
      list.appendChild(empty);
    } else {
      for (const c of clips) {
        const row = document.createElement("div");
        const isActive = (s.active_clip_id || activeClip(s)?.id) === c.id;
        row.className = "clip-item" + (isActive ? " active" : "");
        const left = document.createElement("div");
        const title = document.createElement("div");
        title.textContent = `${c.label || c.id}${isActive ? " · " + t("activeClip") : ""}`;
        const meta = document.createElement("div");
        meta.className = "clip-meta";
        const bits = [c.provider || "?", c.model || "", c.file || ""];
        if (c.chained) bits.push(t("chained"));
        if (c.camera_lock) bits.push(t("cameraLock"));
        if (c.segment_mode) bits.push(t("mode_" + c.segment_mode));
        if (c.subclip_count) bits.push(`${c.subclip_count}×5s`);
        if (c.is_mock) bits.push("mock");
        meta.textContent = bits.filter(Boolean).join(" · ");
        if (c.chained) meta.classList.add("chain-tag");
        if (c.camera_lock) meta.classList.add("lock-tag");
        left.appendChild(title);
        left.appendChild(meta);
        if (c.note) {
          const note = document.createElement("div");
          note.className = "clip-meta";
          note.textContent = c.note;
          left.appendChild(note);
        }
        // Partial regen (subclips) — chips + optional free text
        const subs = c.subclips || [];
        if (subs.length > 1) {
          const regenRow = document.createElement("div");
          regenRow.className = "regen-row";
          const regenLab = document.createElement("span");
          regenLab.className = "mini";
          regenLab.textContent = t("regenSubclips") + ":";
          regenRow.appendChild(regenLab);
          const chipWrap = document.createElement("div");
          chipWrap.className = "regen-chips";
          const selected = new Set();
          const regenIn = document.createElement("input");
          regenIn.type = "text";
          regenIn.className = "regen-input";
          regenIn.placeholder = t("regenPlaceholder");
          regenIn.title = t("regenHelp");
          const syncInput = () => {
            regenIn.value = [...selected].sort((a, b) => a - b).join(",");
          };
          for (let i = 0; i < subs.length; i++) {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "regen-chip";
            chip.textContent = String(i);
            chip.title = t("regenChipTitle", { i, sec: Math.round(Number(subs[i].duration) || 5) });
            chip.onclick = (ev) => {
              ev.stopPropagation();
              if (selected.has(i)) {
                selected.delete(i);
                chip.classList.remove("on");
              } else {
                selected.add(i);
                chip.classList.add("on");
              }
              syncInput();
            };
            chipWrap.appendChild(chip);
          }
          regenRow.appendChild(chipWrap);
          regenRow.appendChild(regenIn);
          const bReg = document.createElement("button");
          bReg.type = "button";
          bReg.className = "ghost";
          bReg.textContent = t("btnRegenParts");
          bReg.onclick = (ev) => {
            ev.stopPropagation();
            const raw = regenIn.value.trim() || [...selected].join(",");
            regenSubclips(s.id, c.id, raw).catch((e) => setStatus(e.message));
          };
          regenRow.appendChild(bReg);
          left.appendChild(regenRow);
        }
        const acts = document.createElement("div");
        acts.className = "clip-actions";
        const bUse = document.createElement("button");
        bUse.type = "button";
        bUse.textContent = t("btnUseClip");
        bUse.disabled = isActive || !!c.is_mock;
        bUse.onclick = (ev) => {
          ev.stopPropagation();
          selectClip(s.id, c.id).catch((e) => setStatus(e.message));
        };
        const bPrev = document.createElement("button");
        bPrev.type = "button";
        bPrev.className = "ghost";
        bPrev.textContent = t("btnShow");
        bPrev.onclick = (ev) => {
          ev.stopPropagation();
          state.selectedSegId = s.id;
          showVideo(s, c);
        };
        const bRm = document.createElement("button");
        bRm.type = "button";
        bRm.className = "danger ghost";
        bRm.textContent = t("btnDelClip");
        bRm.onclick = (ev) => {
          ev.stopPropagation();
          deleteClip(s.id, c.id).catch((e) => setStatus(e.message));
        };
        acts.appendChild(bUse);
        acts.appendChild(bPrev);
        acts.appendChild(bRm);
        row.appendChild(left);
        row.appendChild(acts);
        list.appendChild(row);
      }
    }
    mats.appendChild(list);
    card.appendChild(mats);

    if (activeClip(s)?.composed_prompt) {
      const n = document.createElement("div");
      n.className = "mini";
      const cp = activeClip(s).composed_prompt;
      const cut = cp.slice(0, 160) + (cp.length > 160 ? "…" : "");
      n.textContent = t("sentBundle") + ": " + cut;
      card.appendChild(n);
    }

    root.appendChild(card);
  }
}


function applyPlayRate(rate) {
  const r = Number(rate);
  state.playRate = Number.isFinite(r) && r > 0 ? r : 1;
  const a = $("audio");
  if (a) a.playbackRate = state.playRate;
  forEachVideoLayer((v) => {
    v.playbackRate = state.playRate;
  });
  try {
    localStorage.setItem("mfw.playRate", String(state.playRate));
  } catch (_) {}
}

function onWavePointerMove(ev) {
  if (!state.drag || !state.project) return;
  const wrap = $("waveWrap");
  const rect = wrap.getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
  const tcur = xRatioToTime(x);
  const d = state.drag;
  const seg = (state.project.segments || []).find((s) => s.id === d.sid);
  if (!seg) return;
  d.moved = true;
  const minLen = 0.08;
  const dur = duration();
  if (d.edge === "left") {
    seg.t0 = Math.min(tcur, seg.t1 - minLen);
    if (dur > 0) seg.t0 = Math.max(0, seg.t0);
  } else if (d.edge === "right") {
    seg.t1 = Math.max(tcur, seg.t0 + minLen);
    if (dur > 0) seg.t1 = Math.min(dur, seg.t1);
  } else if (d.edge === "move") {
    const dx = ev.clientX - d.originX;
    const dt = (dx / rect.width) * ensureView().span;
    let nt0 = d.originT0 + dt;
    let nt1 = d.originT1 + dt;
    const len = d.originT1 - d.originT0;
    if (nt0 < 0) {
      nt0 = 0;
      nt1 = len;
    }
    if (dur > 0 && nt1 > dur) {
      nt1 = dur;
      nt0 = dur - len;
    }
    seg.t0 = nt0;
    seg.t1 = nt1;
  }
  // live band redraw
  renderWave();
}

async function onWavePointerUp(ev) {
  if (!state.drag) return;
  const d = state.drag;
  state.drag = null;
  document.querySelectorAll(".seg-band.dragging").forEach((el) => el.classList.remove("dragging"));
  if (!d.moved) {
    selectSegment(d.sid, { focusPrompt: false });
    return;
  }
  state._suppressClick = true;
  const seg = (state.project.segments || []).find((s) => s.id === d.sid);
  if (!seg) return;
  try {
    const updated = await api(
      `/api/projects/${state.project.id}/segments/${d.sid}/times`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ t0: seg.t0, t1: seg.t1 }),
      }
    );
    Object.assign(seg, updated);
    renderWave();
    renderSegments();
    setStatus(t("statusResized", { a: fmt(seg.t0), b: fmt(seg.t1) }));
    commitHistory("resize");
  } catch (e) {
    setStatus(e.message);
    await loadProject(state.project.id);
  }
}

function ensureFlowerSparks() {
  const root = $("flowerSparks");
  if (!root) return;
  root.textContent = "";
  const n = 20;
  for (let i = 0; i < n; i++) {
    const sp = document.createElement("span");
    sp.className = "flower-spark";
    const ang = (Math.PI * 2 * i) / n + (Math.random() * 0.4 - 0.2);
    const dist = 80 + Math.random() * 100;
    sp.style.setProperty("--dx", `${Math.cos(ang) * dist}px`);
    sp.style.setProperty("--dy", `${Math.sin(ang) * dist}px`);
    sp.style.animationDelay = `${0.04 + Math.random() * 0.28}s`;
    root.appendChild(sp);
  }
}

function resetFlowerLoadVisual() {
  const fl = $("flowerLoad");
  if (!fl) return;
  fl.classList.remove(
    "stage-1-on",
    "stage-2-on",
    "stage-3-on",
    "is-complete",
    "is-scatter"
  );
  const sparks = $("flowerSparks");
  if (sparks) sparks.textContent = "";
}

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Floating flower only.
 * While waiting: loop petal unfold 1→2→3→reset.
 * On success finish: full bloom → glow → scatter.
 * On fail finish: fade out without scatter.
 */
function showGenLoader() {
  const el = $("genLoader");
  const fl = $("flowerLoad");
  if (!el) return { finish: async () => {} };

  resetFlowerLoadVisual();
  el.hidden = false;
  el.classList.remove("hidden", "is-leaving");
  el.setAttribute("aria-hidden", "false");

  let stopLoop = false;
  let loopPromise = Promise.resolve();

  const setStages = (n) => {
    if (!fl) return;
    fl.classList.toggle("stage-1-on", n >= 1);
    fl.classList.toggle("stage-2-on", n >= 2);
    fl.classList.toggle("stage-3-on", n >= 3);
  };

  const runLoop = async () => {
    // petal unfold cycle until stopLoop
    while (!stopLoop && fl) {
      setStages(0);
      await sleepMs(120);
      if (stopLoop) break;
      setStages(1);
      await sleepMs(720);
      if (stopLoop) break;
      setStages(2);
      await sleepMs(720);
      if (stopLoop) break;
      setStages(3);
      await sleepMs(980);
    }
  };

  loopPromise = runLoop();

  return {
    async finish(ok = true) {
      stopLoop = true;
      try {
        await loopPromise;
      } catch (_) {}
      if (!fl || !el) return;

      if (ok) {
        // full bloom → glow → scatter (only on success)
        setStages(3);
        await sleepMs(80);
        ensureFlowerSparks();
        fl.classList.add("is-complete");
        await sleepMs(580);
        fl.classList.add("is-scatter");
        await sleepMs(950);
      } else {
        // fail: soft fade, no scatter
        await sleepMs(120);
      }

      el.classList.add("is-leaving");
      await sleepMs(340);
      el.hidden = true;
      el.classList.add("hidden");
      el.classList.remove("is-leaving");
      el.setAttribute("aria-hidden", "true");
      resetFlowerLoadVisual();
    },
  };
}

async function generateSeg(sid, promptText) {
  if (state.genInflight.has(sid)) {
    setStatus(t("statusGenBusy"));
    return;
  }
  state.genInflight.add(sid);
  renderSegments();
  const loader = showGenLoader();
  let ok = false;
  try {
    if (promptText != null) {
      await api(`/api/projects/${state.project.id}/segments/${sid}/prompt`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: promptText }),
      });
    }
    setStatus(t("statusGenerating"));
    const data = await api(`/api/projects/${state.project.id}/segments/${sid}/generate`, {
      method: "POST",
    });
    await loadProject(state.project.id);
    state.selectedSegId = sid;
    renderSegments();
    invalidateClipCache();
    prefetchAdoptedClips().catch(() => {});
    showVideo(data.segment);
    const ch = data.clip?.chained || data.segment?.video?.chained;
    const uref = data.clip?.user_ref_image || data.segment?.video?.user_ref_image;
    const clock = data.clip?.camera_lock || data.segment?.camera_lock;
    const base = t("statusGenOk", { provider: data.segment.video?.provider || "?" });
    let msg = base;
    if (uref) msg += " · " + t("statusGenWithRef");
    else if (ch) msg += " · " + t("statusChain");
    if (clock) msg += " · " + t("statusCameraLockOn");
    setStatus(msg);
    commitHistory("generate");
    ok = true;
  } catch (e) {
    setStatus(t("statusGenFail", { err: e.message }));
    ok = false;
  } finally {
    await loader.finish(ok);
    state.genInflight.delete(sid);
    renderSegments();
  }
}

async function unmatchSeg(sid) {
  const reason = window.prompt(
    t("unmatchReasonPrompt"),
    "other"
  );
  if (reason === null) return;
  const note = window.prompt(t("unmatchPrompt"), "") ?? "";
  try {
    await api(`/api/projects/${state.project.id}/segments/${sid}/unmatch-v2`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: (reason || "other").trim() || "other",
        editor_note: note,
        editor_keywords: [],
      }),
    });
    await loadProject(state.project.id);
    setStatus(t("statusUnmatchOk"));
    commitHistory("unmatch");
  } catch (e) {
    setStatus(t("statusUnmatchFail", { err: e.message }));
  }
}

async function regenSubclips(sid, clipId, rawIndices) {
  const indices = String(rawIndices || "")
    .split(/[\s,]+/)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => parseInt(x, 10))
    .filter((n) => Number.isFinite(n));
  if (!indices.length) {
    setStatus(t("statusRegenNeedIdx"));
    return;
  }
  setStatus(t("statusRegenBusy", { n: indices.join(",") }));
  try {
    const data = await api(
      `/api/projects/${state.project.id}/segments/${sid}/clips/${clipId}/regen-subclips`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ indices }),
      }
    );
    const seg = (state.project.segments || []).find((x) => x.id === sid);
    if (seg && data.segment) Object.assign(seg, data.segment);
    commitHistory("regen-subclips");
    renderSegments();
    setStatus(t("statusRegenOk"));
  } catch (e) {
    setStatus(t("statusRegenFail", { err: e.message }));
  }
}

function activeClip(seg) {
  if (!seg) return null;
  const clips = seg.clips || [];
  if (seg.active_clip_id) {
    const hit = clips.find((c) => c.id === seg.active_clip_id);
    if (hit) return hit;
  }
  if (seg.video?.file) return seg.video;
  return clips.length ? clips[clips.length - 1] : null;
}

function clipUrl(file) {
  return `/api/projects/${state.project.id}/clips/${encodeURIComponent(file)}?t=${Date.now()}`;
}

function programUrl() {
  return `/api/projects/${state.project.id}/program?t=${Date.now()}`;
}

function adoptedProgram() {
  const segs = [...(state.project?.segments || [])].sort(
    (a, b) => Number(a.t0) - Number(b.t0)
  );
  const items = [];
  for (const s of segs) {
    const c = activeClip(s);
    if (c?.file) items.push({ seg: s, clip: c });
  }
  return items;
}

function forEachVideoLayer(fn) {
  const a = $("videoA");
  const b = $("videoB");
  if (a) fn(a, "A");
  if (b) fn(b, "B");
}

function frontVideo() {
  return state.frontKey === "B" ? $("videoB") : $("videoA");
}

function backVideo() {
  return state.frontKey === "B" ? $("videoA") : $("videoB");
}

function setFrontKey(key) {
  state.frontKey = key === "B" ? "B" : "A";
  const a = $("videoA");
  const b = $("videoB");
  if (a) a.classList.toggle("is-front", state.frontKey === "A");
  if (b) b.classList.toggle("is-front", state.frontKey === "B");
}

function swapVideoLayers() {
  const old = frontVideo();
  if (old) old.pause();
  setFrontKey(state.frontKey === "A" ? "B" : "A");
  return frontVideo();
}

function clearVideoLayers() {
  forEachVideoLayer((v) => {
    try {
      v.pause();
    } catch (_) {}
    v.removeAttribute("src");
    delete v.dataset.clipFile;
    delete v.dataset.kind;
    try {
      v.load();
    } catch (_) {}
  });
  state.previewSegId = null;
  state.previewClipFile = null;
  state.usingProgramFile = false;
  state.preloadNextFile = null;
  state._videoSwitching = false;
  setFrontKey("A");
}

function invalidateClipCache() {
  for (const url of state.clipBlobCache.values()) {
    try {
      URL.revokeObjectURL(url);
    } catch (_) {}
  }
  state.clipBlobCache.clear();
  state.clipCacheFp = "";
  state.preloadNextFile = null;
}

function clipCacheFingerprint() {
  if (!state.project) return "";
  const files = adoptedProgram()
    .map((it) => it.clip.file)
    .filter(Boolean)
    .sort();
  return `${state.project.id}|${files.join(",")}`;
}

async function ensureClipBlob(file) {
  if (!file || !state.project) return null;
  if (state.clipBlobCache.has(file)) return state.clipBlobCache.get(file);
  const res = await fetch(
    `/api/projects/${state.project.id}/clips/${encodeURIComponent(file)}`
  );
  if (!res.ok) throw new Error(`clip fetch ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  state.clipBlobCache.set(file, url);
  return url;
}

/** Prefetch adopted clip files as Blob object URLs. Rebuilds when set changes. */
async function prefetchAdoptedClips() {
  if (!state.project) return;
  const fp = clipCacheFingerprint();
  const want = new Set(
    adoptedProgram()
      .map((it) => it.clip.file)
      .filter(Boolean)
  );
  if (fp !== state.clipCacheFp) {
    for (const [f, url] of [...state.clipBlobCache.entries()]) {
      if (!want.has(f)) {
        try {
          URL.revokeObjectURL(url);
        } catch (_) {}
        state.clipBlobCache.delete(f);
      }
    }
    state.clipCacheFp = fp;
  }
  await Promise.all(
    [...want].map((f) =>
      ensureClipBlob(f).catch(() => null)
    )
  );
}

function mediaSrcForClip(file) {
  return state.clipBlobCache.get(file) || clipUrl(file);
}

function waitVideoReady(videoEl, timeoutMs = 12000) {
  if (!videoEl) return Promise.reject(new Error("no video"));
  if (videoEl.readyState >= 2) return Promise.resolve(videoEl);
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (ok, err) => {
      if (done) return;
      done = true;
      videoEl.removeEventListener("loadeddata", onOk);
      videoEl.removeEventListener("canplay", onOk);
      videoEl.removeEventListener("error", onErr);
      clearTimeout(timer);
      if (ok) resolve(videoEl);
      else reject(err || new Error("video load failed"));
    };
    const onOk = () => finish(true);
    const onErr = () => finish(false, new Error("video error"));
    const timer = setTimeout(() => finish(false, new Error("video load timeout")), timeoutMs);
    videoEl.addEventListener("loadeddata", onOk);
    videoEl.addEventListener("canplay", onOk);
    videoEl.addEventListener("error", onErr);
  });
}

async function loadClipInto(videoEl, file, { force = false } = {}) {
  if (!videoEl || !file) throw new Error("loadClipInto: missing args");
  if (!force && videoEl.dataset.clipFile === file && videoEl.readyState >= 2 && videoEl.src) {
    videoEl.playbackRate = state.playRate;
    return videoEl;
  }
  let url = state.clipBlobCache.get(file);
  if (!url) {
    try {
      url = await ensureClipBlob(file);
    } catch (_) {
      url = clipUrl(file);
    }
  }
  videoEl.dataset.clipFile = file;
  videoEl.dataset.kind = "clip";
  videoEl.src = url;
  videoEl.muted = true;
  videoEl.playbackRate = state.playRate;
  videoEl.load();
  await waitVideoReady(videoEl);
  videoEl.playbackRate = state.playRate;
  return videoEl;
}

function nextAdoptedAfter(segId) {
  const prog = adoptedProgram();
  const i = prog.findIndex((it) => it.seg.id === segId);
  if (i < 0 || i >= prog.length - 1) return null;
  return prog[i + 1];
}

/** Preload next adopted segment into the back buffer (no visible src thrash). */
function preloadNextSegment(currentSeg) {
  if (!currentSeg || state.usingProgramFile || state.previewMode !== "program") return;
  const next = nextAdoptedAfter(currentSeg.id);
  const back = backVideo();
  if (!back) return;
  if (!next?.clip?.file) {
    state.preloadNextFile = null;
    return;
  }
  if (back.dataset.clipFile === next.clip.file && back.readyState >= 2) {
    state.preloadNextFile = next.clip.file;
    return;
  }
  const token = ++state._preloadToken;
  state.preloadNextFile = next.clip.file;
  loadClipInto(back, next.clip.file)
    .then((el) => {
      if (token !== state._preloadToken) return;
      try {
        el.currentTime = 0;
      } catch (_) {}
      el.pause();
      el.muted = true;
    })
    .catch(() => {
      if (token === state._preloadToken) state.preloadNextFile = null;
    });
}

function applySyncMuteState() {
  const sync = $("syncMusic")?.checked !== false;
  state.syncMusic = sync;
  forEachVideoLayer((v) => {
    v.muted = sync;
    v.controls = !sync && v.classList.contains("is-front");
  });
}

function segmentAtTime(tcur, { requireClip = true } = {}) {
  const segs = [...(state.project?.segments || [])].sort(
    (a, b) => Number(a.t0) - Number(b.t0)
  );
  for (const s of segs) {
    const t0 = Number(s.t0);
    const t1 = Number(s.t1);
    if (tcur >= t0 - 0.02 && tcur < t1 - 0.001) {
      if (requireClip && !activeClip(s)) continue;
      return s;
    }
  }
  // tiny tolerance at exact end of last adopted
  for (let i = segs.length - 1; i >= 0; i--) {
    const s = segs[i];
    if (Math.abs(tcur - Number(s.t1)) < 0.04) {
      if (requireClip && !activeClip(s)) continue;
      return s;
    }
  }
  return null;
}

function showVideo(seg, clip, { seekAudio = false } = {}) {
  const c = clip || activeClip(seg);
  if (!c?.file || !state.project) return;
  state.usingProgramFile = false;
  const v = frontVideo();
  if (!v) return;
  applySyncMuteState();
  state.previewSegId = seg.id;
  state.previewClipFile = c.file;
  const needLoad = v.dataset.clipFile !== c.file || !v.src;
  if (needLoad) {
    state._videoSwitching = true;
    loadClipInto(v, c.file)
      .then(() => {
        state._videoSwitching = false;
      })
      .catch(() => {
        state._videoSwitching = false;
      });
  }
  const audio = $("audio");
  const sync = $("syncMusic")?.checked !== false;
  if (seekAudio && Number.isFinite(seg.t0) && sync) {
    audio.currentTime = seg.t0;
  }
}

async function playSegmentWithMusic(seg) {
  const c = activeClip(seg);
  if (!c?.file) {
    setStatus(t("statusNeedSeg"));
    return;
  }
  const syncEl = $("syncMusic");
  if (syncEl) syncEl.checked = true;
  state.syncMusic = true;
  state.previewMode = "segment";
  state.usingProgramFile = false;
  const audio = $("audio");
  const v = frontVideo();
  applyPlayRate(state.playRate);
  state.previewSegId = seg.id;
  state.previewClipFile = c.file;
  try {
    await loadClipInto(v, c.file);
  } catch (e) {
    setStatus(e.message);
    return;
  }
  applySyncMuteState();
  audio.currentTime = seg.t0;
  try {
    v.currentTime = 0;
  } catch (_) {}
  v.muted = true;
  await Promise.all([audio.play().catch(() => {}), v.play().catch(() => {})]);
  setStatus(t("statusPlaySync", { a: fmt(seg.t0), b: fmt(seg.t1) }));
  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
}

async function playExportedProgram() {
  const meta = state.project?.program;
  if (!meta?.file || !state.project) return false;
  // Probe that the file is actually available
  try {
    const head = await fetch(programUrl(), { method: "GET", headers: { Range: "bytes=0-1" } });
    if (!head.ok && head.status !== 206) return false;
  } catch (_) {
    return false;
  }

  const prog = adoptedProgram();
  const t0 = Number(meta.t0 ?? prog[0]?.seg.t0) || 0;
  const t1 = Number(meta.t1 ?? prog[prog.length - 1]?.seg.t1) || t0;
  const syncEl = $("syncMusic");
  if (syncEl) syncEl.checked = true;
  state.syncMusic = true;
  state.previewMode = "program";
  state.usingProgramFile = true;
  state.previewSegId = null;
  state.previewClipFile = null;
  state.preloadNextFile = null;

  const v = frontVideo();
  const back = backVideo();
  if (back) {
    try {
      back.pause();
    } catch (_) {}
  }
  v.dataset.kind = "program";
  delete v.dataset.clipFile;
  v.src = programUrl();
  v.muted = true;
  v.playbackRate = state.playRate;
  v.load();
  try {
    await waitVideoReady(v);
  } catch (_) {
    state.usingProgramFile = false;
    return false;
  }

  const audio = $("audio");
  applyPlayRate(state.playRate);
  audio.currentTime = t0;
  try {
    v.currentTime = 0;
  } catch (_) {}
  await Promise.all([audio.play().catch(() => {}), v.play().catch(() => {})]);
  setStatus(t("statusPlayProgramFile", { a: fmt(t0), b: fmt(t1) }));
  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
  return true;
}

async function playProgramLive() {
  const prog = adoptedProgram();
  if (!prog.length) {
    setStatus(t("statusNoAdopted"));
    return;
  }
  const syncEl = $("syncMusic");
  if (syncEl) syncEl.checked = true;
  state.syncMusic = true;
  state.previewMode = "program";
  state.usingProgramFile = false;
  const first = prog[0];
  const last = prog[prog.length - 1];
  await prefetchAdoptedClips();
  const v = frontVideo();
  applyPlayRate(state.playRate);
  state.previewSegId = first.seg.id;
  state.previewClipFile = first.clip.file;
  try {
    await loadClipInto(v, first.clip.file);
  } catch (e) {
    setStatus(e.message);
    return;
  }
  applySyncMuteState();
  const audio = $("audio");
  audio.currentTime = Number(first.seg.t0);
  try {
    v.currentTime = 0;
  } catch (_) {}
  v.muted = true;
  preloadNextSegment(first.seg);
  await Promise.all([audio.play().catch(() => {}), v.play().catch(() => {})]);
  setStatus(t("statusPlayProgram", { a: fmt(first.seg.t0), b: fmt(last.seg.t1) }));
  cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
}

async function playProgram() {
  const prog = adoptedProgram();
  if (!prog.length) {
    setStatus(t("statusNoAdopted"));
    return;
  }
  // Prefer single stitched program.mp4 when metadata + file exist
  if (state.project?.program?.file) {
    const ok = await playExportedProgram();
    if (ok) return;
  }
  await playProgramLive();
}

async function exportProgramStitch() {
  if (!state.project) return;
  if (state.programExporting) return;
  if (!adoptedProgram().length) {
    setStatus(t("statusNoAdopted"));
    return;
  }
  state.programExporting = true;
  const btn = $("btnExportProgram");
  if (btn) btn.disabled = true;
  setStatus(t("statusExporting"));
  try {
    const data = await api(`/api/projects/${state.project.id}/program/export`, {
      method: "POST",
    });
    if (data.project) state.project = data.project;
    else if (data.program) state.project.program = data.program;
    const n = data.program?.clip_count ?? "?";
    const sec = data.program?.duration_sec ?? "?";
    setStatus(t("statusExportOk", { n, sec }));
    commitHistory("export-program");
    await playExportedProgram();
  } catch (e) {
    setStatus(t("statusExportFail", { err: e.message }));
  } finally {
    state.programExporting = false;
    if (btn) btn.disabled = false;
  }
}

async function refreshCanvaStatus() {
  const line = $("canvaStatusLine");
  try {
    const st = await api("/api/canva/status");
    state.canva = st;
    if (!line) return st;
    if (!st.configured) {
      line.textContent = t("statusCanvaNeedConfig");
    } else if (st.connected) {
      line.textContent = t("statusCanvaConnected");
    } else {
      line.textContent = t("statusCanvaDisconnected");
    }
    return st;
  } catch (e) {
    if (line) line.textContent = e.message;
    return null;
  }
}

async function connectCanva() {
  const st = (await refreshCanvaStatus()) || {};
  if (!st.configured) {
    setStatus(t("statusCanvaNeedConfig"));
    return;
  }
  const data = await api("/api/canva/authorize");
  if (!data.authorize_url) throw new Error("no authorize_url");
  window.open(data.authorize_url, "canva_oauth", "width=520,height=720");
  setStatus(t("statusCanvaNeedConnect"));
}

async function disconnectCanva() {
  await api("/api/canva/disconnect", { method: "POST", body: "{}" });
  await refreshCanvaStatus();
  setStatus(t("statusCanvaDisconnected"));
}

async function sendToCanva() {
  if (!state.project?.id) return;
  const st = (await refreshCanvaStatus()) || {};
  if (!st.configured) {
    setStatus(t("statusCanvaNeedConfig"));
    return;
  }
  if (!st.connected && !st.token_valid) {
    setStatus(t("statusCanvaNeedConnect"));
    return;
  }
  const btn = $("btnCanvaSend");
  if (btn) btn.disabled = true;
  setStatus(t("statusCanvaSending"));
  try {
    let body = { what: "program", open_design: true };
    if (!state.project?.program?.file) {
      const sid = state.previewSegId || state.selectedSegId;
      if (sid) body = { what: "segment_active", segment_id: sid, open_design: true };
      else throw new Error(t("statusNoAdopted"));
    }
    const data = await api(`/api/projects/${state.project.id}/canva/send`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const edit = data.design?.edit_url;
    const lib = data.library_url;
    let msg = t("statusCanvaOk");
    if (data.note) msg += ` · ${data.note}`;
    if (data.upload?.asset_id) msg += ` · id ${data.upload.asset_id}`;
    setStatus(msg);
    if (edit) window.open(edit, "_blank");
    else if (lib) window.open(lib, "_blank");
  } catch (e) {
    setStatus(t("statusCanvaFail", { err: e.message }));
  } finally {
    if (btn) btn.disabled = false;
  }
}

function syncVideoToMusic() {
  if (!$("syncMusic")?.checked) {
    state.syncMusic = false;
    return;
  }
  state.syncMusic = true;
  if (!state.project) return;
  const audio = $("audio");
  const v = frontVideo();
  if (!v) return;
  const tcur = audio.currentTime || 0;

  // Single-file program.mp4 path (video timeline starts at program.t0)
  if (state.usingProgramFile && state.project.program) {
    const meta = state.project.program;
    const t0 = Number(meta.t0) || 0;
    const durSec = Number(meta.duration_sec);
    const t1 = Number.isFinite(durSec) && durSec > 0 ? t0 + durSec : Number(meta.t1);
    const rel = Math.max(0, tcur - t0);
    if (tcur < t0 - 0.05 || (Number.isFinite(t1) && tcur > t1 + 0.08)) {
      if (!v.paused) v.pause();
      return;
    }
    if (state._videoSwitching) return;
    if (Math.abs((v.currentTime || 0) - rel) > 0.18) {
      try {
        v.currentTime = rel;
      } catch (_) {}
    }
    v.muted = true;
    if (!audio.paused && v.paused) v.play().catch(() => {});
    if (audio.paused && !v.paused) v.pause();
    return;
  }

  let seg = null;
  if (state.previewMode === "segment" && state.previewSegId) {
    seg = (state.project.segments || []).find((s) => s.id === state.previewSegId);
    if (seg) {
      const t0 = Number(seg.t0);
      const t1 = Number(seg.t1);
      if (tcur < t0 - 0.05 || tcur > t1 + 0.05) {
        if (!v.paused) v.pause();
        return;
      }
    }
  } else {
    // program mode: follow whichever adopted segment owns this time
    state.previewMode = "program";
    seg = segmentAtTime(tcur, { requireClip: true });
  }

  if (!seg) {
    if (!v.paused) v.pause();
    return;
  }

  const c = activeClip(seg);
  if (!c?.file) {
    if (!v.paused) v.pause();
    return;
  }

  // Switch clip when entering another adopted segment (double-buffer swap if ready)
  if (state.previewSegId !== seg.id || state.previewClipFile !== c.file) {
    const rel0 = Math.max(0, tcur - Number(seg.t0));
    const back = backVideo();
    const canSwap =
      state.previewMode === "program" &&
      back &&
      back.dataset.clipFile === c.file &&
      back.readyState >= 2;

    state.previewSegId = seg.id;
    state.previewClipFile = c.file;

    if (canSwap) {
      const front = swapVideoLayers();
      try {
        front.currentTime = rel0;
      } catch (_) {}
      front.muted = true;
      front.playbackRate = state.playRate;
      if (!audio.paused) front.play().catch(() => {});
      state._videoSwitching = false;
      preloadNextSegment(seg);
      return;
    }

    // Fallback: load into front (or back then swap when ready)
    state._videoSwitching = true;
    v.muted = true;
    loadClipInto(v, c.file, { force: true })
      .then((el) => {
        try {
          el.currentTime = rel0;
        } catch (_) {}
        state._videoSwitching = false;
        if (!audio.paused) el.play().catch(() => {});
        if (state.previewMode === "program") preloadNextSegment(seg);
      })
      .catch(() => {
        state._videoSwitching = false;
      });
    return;
  }

  if (state._videoSwitching) return;

  const t0 = Number(seg.t0);
  const t1 = Number(seg.t1);
  const rel = Math.max(0, tcur - t0);
  if (Math.abs((v.currentTime || 0) - rel) > 0.18) {
    try {
      v.currentTime = rel;
    } catch (_) {}
  }
  v.muted = true;
  if (!audio.paused && v.paused) {
    v.play().catch(() => {});
  }
  if (audio.paused && !v.paused) {
    v.pause();
  }
  if (state.previewMode === "segment" && tcur >= t1 - 0.03) {
    v.pause();
  }
  // Keep next segment warm in the back buffer while current plays
  if (state.previewMode === "program" && !state.usingProgramFile) {
    const next = nextAdoptedAfter(seg.id);
    if (next?.clip?.file && state.preloadNextFile !== next.clip.file) {
      preloadNextSegment(seg);
    }
  }
}

async function selectClip(sid, clipId) {
  const data = await api(`/api/projects/${state.project.id}/segments/${sid}/clips/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clip_id: clipId }),
  });
  // patch local
  const seg = (state.project.segments || []).find((s) => s.id === sid);
  if (seg) {
    Object.assign(seg, data.segment);
  }
  state.selectedSegId = sid;
  invalidateClipCache();
  prefetchAdoptedClips().catch(() => {});
  renderSegments();
  showVideo(data.segment, data.clip);
  setStatus(t("statusClipActive"));
  commitHistory("clip-select");
}

async function deleteClip(sid, clipId) {
  const data = await api(
    `/api/projects/${state.project.id}/segments/${sid}/clips/${encodeURIComponent(clipId)}`,
    { method: "DELETE" }
  );
  const seg = (state.project.segments || []).find((s) => s.id === sid);
  if (seg) Object.assign(seg, data.segment);
  invalidateClipCache();
  prefetchAdoptedClips().catch(() => {});
  renderSegments();
  if (data.segment?.video?.file) showVideo(data.segment);
  else clearVideoLayers();
  setStatus(t("statusClipDeleted"));
  commitHistory("clip-delete");
}

async function onWaveClick(ev) {
  if (state._suppressClick) {
    state._suppressClick = false;
    return;
  }
  if (!state.project?.digest) {
    setStatus(t("statusImportFirst"));
    return;
  }
  const wrap = $("waveWrap");
  const rect = wrap.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const ratio = Math.min(1, Math.max(0, x / rect.width));
  const tclick = xRatioToTime(ratio);

  // Click on a segment band → jump to that segment's editor (no pin).
  const hit = segmentAtTime(tclick);
  if (hit) {
    $("audio").currentTime = hit.t0;
    updatePlayhead();
    selectSegment(hit.id, { focusPrompt: true });
    setStatus(t("statusSegSelected", { a: fmt(hit.t0), b: fmt(hit.t1) }));
    return;
  }

  // Empty waveform: seek only (pins are M).
  $("audio").currentTime = tclick;
  updatePlayhead();
}

function onGlobalKeydown(ev) {
  if (isTypingTarget(ev.target)) return;

  const mod = ev.metaKey || ev.ctrlKey;
  // Undo / Redo — ⌘Z / ⌘⇧Z / ⌘Y (Ctrl on non-Mac)
  if (mod && !ev.altKey && (ev.key === "z" || ev.key === "Z")) {
    ev.preventDefault();
    if (ev.shiftKey) redoEdit().catch((e) => setStatus(e.message));
    else undoEdit().catch((e) => setStatus(e.message));
    return;
  }
  if (mod && !ev.altKey && (ev.key === "y" || ev.key === "Y")) {
    ev.preventDefault();
    redoEdit().catch((e) => setStatus(e.message));
    return;
  }
  if (mod || ev.altKey) return;

  const key = ev.key;
  if (key === " " || key === "Spacebar") {
    ev.preventDefault();
    togglePlay();
    return;
  }
  if (key === "r" || key === "R") {
    ev.preventDefault();
    seekToStart();
    return;
  }
  if (key === "p" || key === "P") {
    ev.preventDefault();
    placePinAtPlayhead();
    return;
  }
  if (key === "k" || key === "K") {
    ev.preventDefault();
    playFromFrameStart();
    return;
  }
  if (key === "ArrowLeft") {
    ev.preventDefault();
    nudgeSeek(ev.shiftKey ? -1 : -0.1);
    return;
  }
  if (key === "ArrowRight") {
    ev.preventDefault();
    nudgeSeek(ev.shiftKey ? 1 : 0.1);
    return;
  }
  if (key === "+" || key === "=") {
    ev.preventDefault();
    zoomBy(0.82, 0.5);
    return;
  }
  if (key === "-" || key === "_") {
    ev.preventDefault();
    zoomBy(1.22, 0.5);
    return;
  }
  if (key === "Enter") {
    if (state.selectedSegId) {
      ev.preventDefault();
      selectSegment(state.selectedSegId, { focusPrompt: true });
    }
    return;
  }
  if (key === "Backspace" || key === "Delete") {
    if (state.selectedSegId) {
      ev.preventDefault();
      deleteSelectedSegment().catch((e) => setStatus(e.message));
    }
    return;
  }
  if (key === "0" && !ev.shiftKey) {
    ev.preventDefault();
    resetViewFull();
    renderWave();
    setStatus(t("statusZoomReset"));
    return;
  }
  if (key === "l" || key === "L") {
    ev.preventDefault();
    toggleLoopSelected();
    return;
  }
  if (key === "f" || key === "F") {
    ev.preventDefault();
    zoomFitSelected();
    return;
  }
  if (key === "Tab") {
    ev.preventDefault();
    selectSegmentByDelta(ev.shiftKey ? -1 : 1);
    return;
  }
}

function wire() {
  const rateEl = $("playRate");
  if (rateEl) {
    try {
      const saved = localStorage.getItem("mfw.playRate");
      if (saved) rateEl.value = saved;
    } catch (_) {}
    applyPlayRate(rateEl.value);
    rateEl.onchange = () => applyPlayRate(rateEl.value);
  }
  window.addEventListener("pointermove", onWavePointerMove);
  window.addEventListener("pointerup", onWavePointerUp);
  window.addEventListener("pointercancel", onWavePointerUp);

  // Timeline horizontal scrollbar ↔ waveform view
  const sc = $("waveScroll");
  if (sc) {
    sc.addEventListener("input", onWaveScrollInput);
    sc.addEventListener("change", onWaveScrollInput);
  }
  const scr = $("waveScrollRow");
  if (scr) {
    scr.addEventListener(
      "wheel",
      (ev) => {
        if (!state.project?.digest) return;
        ev.preventDefault();
        const v = ensureView();
        const raw =
          Math.abs(ev.deltaX || 0) >= Math.abs(ev.deltaY || 0)
            ? ev.deltaX
            : ev.deltaY;
        let scale = 0.0018;
        if (ev.deltaMode === 1) scale = 0.08;
        if (ev.deltaMode === 2) scale = 0.35;
        // If full view, zoom in a bit first so pan has room
        if (v.dur > 0 && v.span >= v.dur - 0.02) {
          const span = Math.max(Math.min(v.dur * 0.35, v.dur), Math.min(8, v.dur));
          const mid = (v.start + v.end) / 2;
          state.viewStart = Math.max(0, mid - span / 2);
          state.viewEnd = Math.min(v.dur, state.viewStart + span);
          if (state.viewEnd - state.viewStart < span) {
            state.viewStart = Math.max(0, state.viewEnd - span);
          }
          renderWave();
        }
        panViewBy(raw * scale * ensureView().span);
      },
      { passive: false }
    );
  }

  const syncEl = $("syncMusic");
  if (syncEl) {
    syncEl.onchange = () => {
      applySyncMuteState();
    };
  }
  const bpp = $("btnPlayProgram");
  if (bpp) bpp.onclick = () => playProgram().catch((e) => setStatus(e.message));
  const bpm = $("btnPlayWithMusic");
  if (bpm) {
    bpm.onclick = () => {
      const seg =
        (state.project?.segments || []).find((s) => s.id === state.selectedSegId) ||
        (state.project?.segments || []).find((s) => s.id === state.previewSegId);
      if (!seg) {
        setStatus(t("statusNeedSeg"));
        return;
      }
      playSegmentWithMusic(seg).catch((e) => setStatus(e.message));
    };
  }
  const bex = $("btnExportProgram");
  if (bex) {
    bex.onclick = () => exportProgramStitch().catch((e) => setStatus(e.message));
  }
  const bCanva = $("btnCanvaSend");
  if (bCanva) {
    bCanva.onclick = () => sendToCanva().catch((e) => setStatus(t("statusCanvaFail", { err: e.message })));
  }
  const bCanvaConn = $("btnCanvaConnect");
  if (bCanvaConn) {
    bCanvaConn.onclick = () => connectCanva().catch((e) => setStatus(t("statusCanvaFail", { err: e.message })));
  }
  const bCanvaDisc = $("btnCanvaDisconnect");
  if (bCanvaDisc) {
    bCanvaDisc.onclick = () => disconnectCanva().catch((e) => setStatus(t("statusCanvaFail", { err: e.message })));
  }
  window.addEventListener("message", (ev) => {
    if (ev?.data?.type === "canva-connected") {
      refreshCanvaStatus().catch(() => {});
      setStatus(t("statusCanvaConnected"));
    }
  });
  refreshCanvaStatus().catch(() => {});
  $("btnOpenFolder").onclick = () => openCurrentProjectFolder().catch((e) => setStatus(t("statusOpenFolderFail", { err: e.message })));
  $("fileInput").onchange = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await importFile(f);
    } catch (err) {
      setStatus(t("statusImportFail", { err: err.message }));
    }
    e.target.value = "";
  };
  $("projectSelect").onchange = async (e) => {
    const id = e.target.value;
    if (id) await loadProject(id).catch((err) => setStatus(err.message));
  };
  $("btnPlay").onclick = () => togglePlay();
  $("audio").addEventListener("timeupdate", updatePlayhead);
  $("audio").addEventListener("play", () => {
    if ($("syncMusic")?.checked) {
      state.syncMusic = true;
      if (state.previewMode !== "segment") state.previewMode = "program";
    }
    cancelAnimationFrame(state.raf);
    state.raf = requestAnimationFrame(tick);
  });
  $("audio").addEventListener("pause", () => cancelAnimationFrame(state.raf));
  $("waveWrap").addEventListener("click", onWaveClick);
  $("waveWrap").addEventListener(
    "wheel",
    onWaveWheel,
    { passive: false }
  );
  $("waveWrap").addEventListener("dblclick", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    state._suppressClick = true;
    // Alt+double-click keeps old "zoom full" behavior
    if (ev.altKey) {
      resetViewFull();
      renderWave();
      syncWaveScroll();
      setStatus(t("statusZoomReset"));
      return;
    }
    const tt = seekPlayheadToClientX(ev.clientX);
    if (tt != null) {
      setStatus(t("statusSeek", { t: fmt(tt) }));
    }
  });
  document.addEventListener("keydown", onGlobalKeydown);
  $("btnCancelPin").onclick = async () => {
    if (!state.project) return;
    state.project = await api(`/api/projects/${state.project.id}/pin/cancel`, {
      method: "POST",
    });
    updatePinUi();
    renderWave();
    commitHistory("pin-cancel");
    setStatus(t("statusPinCancel"));
  };
  $("btnSaveMeta").onclick = async () => {
    if (!state.project) return;
    state.project = await api(`/api/projects/${state.project.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectMetaBody()),
    });
    commitHistory("meta");
    setStatus(t("statusMetaSaved"));
    refreshTasteHints().catch(() => {});
  };
  for (const r of document.querySelectorAll('input[name="barMode"]')) {
    r.addEventListener("change", async () => {
      applyBarMode(r.value);
      if (!state.project) return;
      await api(`/api/projects/${state.project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectMetaBody({ bar_mode: r.value })),
      });
    });
  }

  $("btnSettings").onclick = () => openSettings(true);
  $("btnSettingsClose").onclick = () => openSettings(false);
  $("settingsBackdrop").onclick = () => openSettings(false);
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.onclick = () => setLang(btn.dataset.lang);
  });

  window.addEventListener("resize", () => renderWave());
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") openSettings(false);
  });
  bindLayoutResize();
}

/** Keep wave/timeline canvas matched to the real window (Chrome --app resize / fullscreen). */
function bindLayoutResize() {
  let raf = 0;
  const kick = () => {
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      raf = 0;
      try {
        renderWave();
      } catch (e) {
        /* ignore mid-teardown */
      }
    });
  };
  window.addEventListener("resize", kick);
  try {
    window.visualViewport?.addEventListener("resize", kick);
    window.visualViewport?.addEventListener("scroll", kick);
  } catch (_) {
    /* older WebKit */
  }
  if (typeof ResizeObserver === "undefined") return;
  const ro = new ResizeObserver(() => kick());
  const waveWrap = $("waveWrap");
  if (waveWrap) ro.observe(waveWrap);
  const layout = document.querySelector(".layout");
  if (layout) ro.observe(layout);
  const stage = document.querySelector(".timeline-stage");
  if (stage) ro.observe(stage);
}

async function refreshVideoBadge() {
  const el = $("videoModelBadge");
  if (!el) return;
  try {
    const h = await api("/api/health");
    state.health = h;
    const prov = String(h.video_provider || "mock").toLowerCase();
    let model = h.video_model || h.xai_model || h.fal_model || "";
    let label = "";
    let title = "";
    el.classList.remove("badge-warn", "badge-muted");

    if (prov === "xai" || prov === "grok") {
      const m = model || "grok-imagine-video";
      const i2v = h.xai_model_i2v || "grok-imagine-video-1.5";
      const authOk = h.xai_auth && h.xai_auth.ok;
      label = authOk ? `xAI · ${m}` : `xAI · ${m} · !`;
      title = authOk
        ? `provider=xai\ntext→video: ${m}\nimage→video: ${i2v}\nauth: ${h.xai_auth?.source || "ok"}`
        : `provider=xai\nmodel: ${m}\nauth: FAIL (${h.xai_auth?.error || h.xai_auth?.relogin_hint || "not ok"})`;
      if (!authOk) el.classList.add("badge-warn");
    } else if (prov === "fal") {
      label = `fal · ${model || "?"}`;
      title = `provider=fal\nmodel: ${model || "?"}`;
    } else {
      label = "mock";
      title = "VIDEO_PROVIDER=mock（ローカル疑似生成）";
      el.classList.add("badge-muted");
    }

    el.textContent = label;
    el.title = title;
    el.setAttribute("aria-label", label);
    // refresh gen button labels if segments already drawn
    if (state.project) renderSegments();
  } catch (e) {
    el.textContent = "—";
    el.title = String(e.message || e);
    el.classList.add("badge-warn");
  }
}

async function boot() {
  state.lang = detectLang();
  wire();
  wireSettingsDrag();
  applyI18nStatic();
  refreshVideoBadge().catch(() => {});
  try {
    const data = await refreshProjectList();
    const projects = data.projects || [];
    let want = null;
    try {
      want = localStorage.getItem("mfw.projectId");
    } catch (_) {}
    if (want && projects.some((p) => p.id === want)) {
      await loadProject(want);
    } else if (projects.length) {
      // prefer project that has segments / audio over empty verify stubs
      const ranked = [...projects].sort((a, b) => {
        const sa = (a.segment_count || 0) * 10 + (a.duration_sec ? 1 : 0);
        const sb = (b.segment_count || 0) * 10 + (b.duration_sec ? 1 : 0);
        if (sb !== sa) return sb - sa;
        return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      });
      await loadProject(ranked[0].id);
    } else {
      await createProject();
    }
    if (state.project) {
      await refreshProjectList(state.project.id);
    }
  } catch (e) {
    setStatus(t("statusBootFail", { err: e.message }));
  }
  setInterval(() => {
    refreshVideoBadge().catch(() => {});
  }, 60000);
}

boot();
