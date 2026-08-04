/* Craft UI — Unmatch reason sheet + affect sliders (no app.js edit required) */
(function () {
  const REASONS = ["emotion", "world", "camera", "style", "episode", "other"];

  const I18N = {
    ja: {
      unmatchWhatDiff: "何が違う？",
      unmatchNoteLab: "メモ（任意）",
      unmatchNotePh: "補足があれば…",
      unmatchNotePhEpisode: "例: くつろぎたかったのに煽られた",
      unmatchEpisodeHint: "求めていた音楽の役割・働きと違うとき（画が悪くなくても可）",
      unmatchRecord: "記録",
      btnCancel: "キャンセル",
      reason_emotion: "感情",
      reason_world: "世界観",
      reason_camera: "カメラ",
      reason_style: "画風",
      reason_episode: "体験の働き",
      reason_other: "その他",
      affectTitle: "気配（任意）",
      affectQuiet: "静けさ",
      affectMoving: "動き",
      affectLow: "沈み",
      affectBright: "明るさ",
      statusUnmatchOk: "Unmatch を記録しました",
      statusUnmatchFail: "Unmatch 失敗: {err}",
      statusAffectSaved: "気配を保存しました",
      statusAffectFail: "気配の保存に失敗: {err}",
      btnUnmatch: "なんか違う",
    },
    en: {
      unmatchWhatDiff: "What feels wrong?",
      unmatchNoteLab: "Note (optional)",
      unmatchNotePh: "Optional detail…",
      unmatchNotePhEpisode: "e.g. wanted calm, got pushy energy",
      unmatchEpisodeHint: "Wrong kind of engagement — even if the picture is fine",
      unmatchRecord: "Save",
      btnCancel: "Cancel",
      reason_emotion: "Emotion",
      reason_world: "World",
      reason_camera: "Camera",
      reason_style: "Style",
      reason_episode: "Engagement",
      reason_other: "Other",
      affectTitle: "Feel (optional)",
      affectQuiet: "Still",
      affectMoving: "Moving",
      affectLow: "Low",
      affectBright: "Bright",
      statusUnmatchOk: "Unmatch recorded",
      statusUnmatchFail: "Unmatch failed: {err}",
      statusAffectSaved: "Feel saved",
      statusAffectFail: "Feel save failed: {err}",
      btnUnmatch: "Unmatch",
    },
    zh: {
      unmatchWhatDiff: "哪里不对？",
      unmatchNoteLab: "备注（可选）",
      unmatchNotePh: "补充说明…",
      unmatchNotePhEpisode: "例：想放松却被煽动",
      unmatchEpisodeHint: "想要的聆听作用不对（画面尚可也可选）",
      unmatchRecord: "记录",
      btnCancel: "取消",
      reason_emotion: "情感",
      reason_world: "世界观",
      reason_camera: "镜头",
      reason_style: "画风",
      reason_episode: "体验作用",
      reason_other: "其他",
      affectTitle: "气息（可选）",
      affectQuiet: "安静",
      affectMoving: "动感",
      affectLow: "低沉",
      affectBright: "明亮",
      statusUnmatchOk: "已记录 Unmatch",
      statusUnmatchFail: "Unmatch 失败: {err}",
      statusAffectSaved: "气息已保存",
      statusAffectFail: "气息保存失败: {err}",
      btnUnmatch: "不对劲",
    },
  };

  function lang() {
    try {
      const s = localStorage.getItem("mfw.lang");
      if (s && I18N[s]) return s;
    } catch (_) {}
    return "ja";
  }

  function t(key, vars) {
    if (window.MFW_I18N && window.MFW_I18N.strings) {
      const L = lang();
      const pack = window.MFW_I18N.strings[L] || window.MFW_I18N.strings.ja || {};
      if (pack[key] != null) {
        let s = pack[key];
        if (vars) for (const [k, v] of Object.entries(vars)) s = String(s).split(`{${k}}`).join(String(v));
        return s;
      }
    }
    let s = (I18N[lang()] || I18N.ja)[key] || I18N.ja[key] || key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = String(s).split(`{${k}}`).join(String(v));
    return s;
  }

  function setStatus(msg) {
    const el = document.getElementById("status");
    if (el) el.textContent = msg;
  }

  function pid() {
    const sel = document.getElementById("projectSelect");
    return (sel && sel.value) || "";
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  function ensureModal() {
    let root = document.getElementById("unmatchModal");
    if (root) return root;
    root = document.createElement("div");
    root.id = "unmatchModal";
    root.className = "unmatch-modal hidden";
    root.hidden = true;
    root.innerHTML = `
      <div class="unmatch-backdrop" data-unmatch-cancel="1"></div>
      <div class="unmatch-sheet" role="dialog" aria-modal="true">
        <h3 id="unmatchTitle"></h3>
        <p class="hint unmatch-lead" id="unmatchLead"></p>
        <div class="unmatch-reasons" id="unmatchReasons"></div>
        <p class="hint unmatch-ep-hint" id="unmatchEpHint" hidden></p>
        <label class="unmatch-note-lab" for="unmatchNote" id="unmatchNoteLab"></label>
        <textarea id="unmatchNote" rows="2"></textarea>
        <div class="unmatch-actions">
          <button type="button" class="ghost" id="unmatchCancel"></button>
          <button type="button" class="primary" id="unmatchOk"></button>
        </div>
      </div>`;
    document.body.appendChild(root);
    return root;
  }

  function openUnmatchUI(sid) {
    const projectId = pid();
    if (!projectId || !sid) return;
    const root = ensureModal();
    root.querySelector("#unmatchTitle").textContent = t("btnUnmatch");
    root.querySelector("#unmatchLead").textContent = t("unmatchWhatDiff");
    root.querySelector("#unmatchNoteLab").textContent = t("unmatchNoteLab");
    const note = root.querySelector("#unmatchNote");
    note.placeholder = t("unmatchNotePh");
    note.value = "";
    root.querySelector("#unmatchCancel").textContent = t("btnCancel");
    root.querySelector("#unmatchOk").textContent = t("unmatchRecord");
    const epHint = root.querySelector("#unmatchEpHint");
    epHint.textContent = t("unmatchEpisodeHint");
    epHint.hidden = true;

    const reasonsEl = root.querySelector("#unmatchReasons");
    reasonsEl.textContent = "";
    let selected = "other";
    for (const r of REASONS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "unmatch-reason-chip" + (r === selected ? " is-on" : "");
      btn.dataset.reason = r;
      btn.textContent = t("reason_" + r);
      btn.onclick = () => {
        selected = r;
        reasonsEl.querySelectorAll(".unmatch-reason-chip").forEach((c) => {
          c.classList.toggle("is-on", c.dataset.reason === selected);
        });
        epHint.hidden = selected !== "episode";
        note.placeholder = selected === "episode" ? t("unmatchNotePhEpisode") : t("unmatchNotePh");
      };
      reasonsEl.appendChild(btn);
    }

    const close = () => {
      root.classList.add("hidden");
      root.hidden = true;
    };

    root.querySelector("#unmatchCancel").onclick = close;
    root.querySelector("[data-unmatch-cancel]").onclick = close;
    root.querySelector("#unmatchOk").onclick = async () => {
      const card = document.querySelector(`.seg-card[data-id="${sid}"]`);
      const body = {
        reason: selected,
        editor_note: note.value || "",
        editor_keywords: [],
      };
      if (card) {
        const a = card.querySelector('input[data-affect="arousal"]');
        const v = card.querySelector('input[data-affect="valence"]');
        if (a && !a.classList.contains("is-unset")) body.arousal = Number(a.value);
        if (v && !v.classList.contains("is-unset")) body.valence = Number(v.value);
      }
      try {
        await api(`/api/projects/${projectId}/segments/${sid}/unmatch-v2`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        close();
        setStatus(t("statusUnmatchOk"));
        const sel = document.getElementById("projectSelect");
        if (sel) sel.dispatchEvent(new Event("change"));
      } catch (e) {
        setStatus(t("statusUnmatchFail", { err: e.message }));
      }
    };

    root.classList.remove("hidden");
    root.hidden = false;
  }

  function injectAffect(card) {
    if (!card || card.querySelector(".affect-row")) return;
    const sid = card.dataset.id;
    if (!sid) return;
    const row = document.createElement("div");
    row.className = "affect-row";
    const title = document.createElement("div");
    title.className = "mini affect-title";
    title.textContent = t("affectTitle");
    row.appendChild(title);

    function mk(key, min, max, step, left, right) {
      const wrap = document.createElement("div");
      wrap.className = "affect-slider-wrap";
      const ends = document.createElement("div");
      ends.className = "affect-ends";
      ends.innerHTML = `<span>${left}</span><span>${right}</span>`;
      const input = document.createElement("input");
      input.type = "range";
      input.min = String(min);
      input.max = String(max);
      input.step = String(step);
      input.value = String((min + max) / 2);
      input.dataset.affect = key;
      input.classList.add("is-unset");
      input.addEventListener("input", () => input.classList.remove("is-unset"));
      input.addEventListener("change", async () => {
        const projectId = pid();
        if (!projectId) return;
        const body = key === "arousal" ? { arousal: Number(input.value) } : { valence: Number(input.value) };
        try {
          await api(`/api/projects/${projectId}/segments/${sid}/affect`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          input.classList.remove("is-unset");
          setStatus(t("statusAffectSaved"));
        } catch (e) {
          setStatus(t("statusAffectFail", { err: e.message }));
        }
      });
      wrap.appendChild(ends);
      wrap.appendChild(input);
      return wrap;
    }

    row.appendChild(mk("arousal", 0, 1, 0.05, t("affectQuiet"), t("affectMoving")));
    row.appendChild(mk("valence", -1, 1, 0.05, t("affectLow"), t("affectBright")));

    const modeRow = card.querySelector(".mode-row");
    if (modeRow) modeRow.insertAdjacentElement("afterend", row);
    else {
      const ta = card.querySelector("textarea");
      if (ta) ta.insertAdjacentElement("afterend", row);
      else card.appendChild(row);
    }
  }

  function wireCard(card) {
    injectAffect(card);
    const actions = card.querySelector(".seg-actions");
    if (!actions || actions.dataset.craftUnmatch === "1") return;
    actions.dataset.craftUnmatch = "1";
    const unBtn = actions.querySelector("button:not(.primary):not(.ghost):not(.danger)");
    if (unBtn) {
      unBtn.addEventListener(
        "click",
        (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          openUnmatchUI(card.dataset.id);
        },
        true
      );
    }
  }

  function scan() {
    document.querySelectorAll(".seg-card").forEach(wireCard);
  }

  function boot() {
    scan();
    const host = document.getElementById("segments");
    if (host) {
      const mo = new MutationObserver(() => scan());
      mo.observe(host, { childList: true, subtree: true });
    }
    window.mfwOpenUnmatch = openUnmatchUI;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(boot, 0));
  } else {
    setTimeout(boot, 0);
  }
})();
