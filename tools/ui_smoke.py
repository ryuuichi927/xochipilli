#!/usr/bin/env python3
"""Click every top-level control in a real Chrome and report what breaks.

The IDE browser blocks fetch() to 127.0.0.1, and pywebview has no CDP, so button
regressions (empty project list, dead "open folder", failing import) were only ever
caught by hand. Usage:

    .venv/bin/python tools/ui_smoke.py [--port 8788] [--keep]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_PORT = 9333


def _wait_targets(timeout: float = 20.0) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2) as r:
                targets = json.loads(r.read().decode("utf-8"))
            pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                return pages
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.3)
    raise RuntimeError("Chrome CDP did not come up")


class Page:
    def __init__(self, ws) -> None:
        self.ws = ws
        self._id = 0

    async def send(self, method: str, params: dict | None = None):
        self._id += 1
        mid = self._id
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") != mid:
                continue
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result") or {}

    async def eval(self, expr: str, *, await_promise: bool = False):
        res = await self.send(
            "Runtime.evaluate",
            {
                "expression": expr,
                "returnByValue": True,
                "awaitPromise": await_promise,
                "userGesture": True,
            },
        )
        if res.get("exceptionDetails"):
            raise RuntimeError(json.dumps(res["exceptionDetails"])[:400])
        return res["result"].get("value")

    async def set_file_input(self, selector: str, path: str) -> None:
        doc = await self.send("DOM.getDocument", {"depth": 1})
        node = await self.send(
            "DOM.querySelector",
            {"nodeId": doc["root"]["nodeId"], "selector": selector},
        )
        await self.send(
            "DOM.setFileInputFiles",
            {"nodeId": node["nodeId"], "files": [path]},
        )


STATUS_JS = "document.getElementById('status').textContent"

OPTIONS_JS = (
    "JSON.stringify([...document.getElementById('projectSelect').options]"
    ".map(o=>[o.value,o.textContent]))"
)


async def _wait_context(p: "Page", timeout: float = 40.0) -> None:
    """Chrome accepts CDP before the tab has a JS context; evaluating too early throws."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if await p.eval("document.readyState"):
                return
        except RuntimeError:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("page never got a JS execution context")


async def restore_flow(p: "Page") -> list[str]:
    """Pick a ☁ (archived) project and watch it come back from iCloud."""
    fails: list[str] = []
    opts = json.loads(await p.eval(OPTIONS_JS) or "[]")
    cold = [o for o in opts if (o[1] or "").startswith("☁")]
    if not cold:
        print("no archived project in the dropdown — nothing to restore")
        return fails
    pid, label = cold[0]
    print(f"selecting {label} ({pid})")
    await p.eval(
        "(()=>{const s=document.getElementById('projectSelect');s.value=%s;"
        "s.dispatchEvent(new Event('change'));})()" % json.dumps(pid)
    )
    seen: list[str] = []
    loaded = False
    for _ in range(300):  # an evicted folder has to download; give it 10 minutes
        await asyncio.sleep(2.0)
        status = await p.eval(STATUS_JS)
        if status and (not seen or seen[-1] != status):
            seen.append(status)
            print(f"  status: {status}")
        got = await p.eval(
            "JSON.stringify({id:(typeof state!=='undefined'&&state.project)?state.project.id:null,"
            "bpm:(typeof state!=='undefined'&&state.project&&state.project.digest)?"
            "state.project.digest.global.tempo_bpm:null,"
            "label:(([...document.getElementById('projectSelect').options]"
            ".find(o=>o.value===%s)||{}).textContent)||''})" % json.dumps(pid)
        )
        got = json.loads(got or "{}")
        if got.get("id") == pid and got.get("bpm"):
            print(f"restored: {got}")
            loaded = True
            if (got.get("label") or "").startswith("☁"):
                fails.append("project loaded but the dropdown still shows it as archived")
            break
    if not loaded:
        fails.append(f"archived project never came back (last status: {seen[-1:] })")
    return fails


async def run(url: str, import_file: str | None = None, only_restore: bool = False) -> int:
    import websockets

    page = None
    deadline = time.time() + 20
    while time.time() < deadline and page is None:
        for t in _wait_targets():
            if url.rstrip("/") in (t.get("url") or "").rstrip("/"):
                page = t
                break
        if page is None:
            time.sleep(0.5)
    page = page or _wait_targets()[0]
    fails: list[str] = []
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024) as ws:
        p = Page(ws)
        await _wait_context(p)
        # A tab that opened before the server answered shows Chrome's error page; the app
        # never boots there and every selector comes back null.
        here = await p.eval("location.href")
        if url.rstrip("/") not in (here or "").rstrip("/"):
            await p.send("Page.navigate", {"url": url})
            await asyncio.sleep(1.5)
            await _wait_context(p)
        for _ in range(80):
            if await p.eval("!!document.getElementById('projectSelect')"):
                break
            await asyncio.sleep(0.5)
        # Boot must populate the project dropdown.
        for _ in range(60):
            n = await p.eval(
                "(document.getElementById('projectSelect')||{options:[]}).options.length"
            )
            if n and n > 1:
                break
            await asyncio.sleep(0.5)
        opts = await p.eval(
            "JSON.stringify([...document.getElementById('projectSelect').options]"
            ".map(o=>[o.value,o.textContent]))"
        )
        opts = json.loads(opts or "[]")
        print(f"dropdown: {len(opts)} entries; first = {opts[0] if opts else None}")
        if not opts:
            fails.append("project dropdown is empty (boot failed)")
        elif opts[0][0] != "__new__":
            fails.append(f"first dropdown entry is not the create action: {opts[0]}")

        err = await p.eval("JSON.stringify(window.__uiErrors||[])")
        console = json.loads(err or "[]")

        if only_restore:
            fails += await restore_flow(p)
            print("----")
            if fails:
                for f in fails:
                    print(f"FAIL {f}")
                return 1
            print("RESTORE_SMOKE_PASS fails=0")
            return 0

        # "create new project" via the dropdown, exactly like a user does it. Everything
        # after this runs inside that throwaway project so no real project is touched.
        before_n = len(opts)
        await p.eval(
            "(()=>{const s=document.getElementById('projectSelect');s.value='__new__';"
            "s.dispatchEvent(new Event('change'));})()"
        )
        await asyncio.sleep(2.5)
        after = json.loads(
            await p.eval(
                "JSON.stringify([...document.getElementById('projectSelect').options]"
                ".map(o=>o.value))"
            )
            or "[]"
        )
        temp_pid = await p.eval("document.getElementById('projectSelect').value")
        print(f"create-new: {before_n} -> {len(after)} entries, selected={temp_pid}")
        if len(after) <= before_n:
            fails.append("selecting the create action did not add a project")
        if temp_pid == "__new__":
            fails.append("dropdown stayed on the create action after creating")
            return 1

        if import_file:
            print(f"importing {import_file} through the real file input …")
            await p.send("DOM.enable")
            # setFileInputFiles already fires "change" — dispatching it again imports twice.
            await p.set_file_input("#fileInput", import_file)
            state = None
            # app.js declares `state` with const, so it is a global lexical binding, not window.state.
            probe = (
                "JSON.stringify({s:document.getElementById('status').textContent,"
                "bpm:(typeof state!=='undefined'&&state.project&&state.project.digest)?"
                "state.project.digest.global.tempo_bpm:null,"
                "peaks:(typeof state!=='undefined'&&state.project&&state.project.digest)?"
                "(state.project.digest.waveform_peaks||[]).length:0,"
                "id:(typeof state!=='undefined'&&state.project)?state.project.id:null})"
            )
            for _ in range(240):  # a track that still lives in iCloud has to download first
                await asyncio.sleep(2.0)
                state = json.loads(await p.eval(probe) or "{}")
                if state.get("bpm") or "失敗" in (state.get("s") or ""):
                    break
            print(f"import result: {state}")
            if not state or not state.get("bpm"):
                fails.append(f"import did not finish: {state}")
            elif not state.get("peaks"):
                fails.append("import produced no waveform peaks")
            elif state.get("id") != temp_pid:
                fails.append(f"import landed in {state.get('id')}, not the new project")

        # Every header/panel button, clicked for real.
        buttons = await p.eval(
            "JSON.stringify([...document.querySelectorAll('button[id]')]"
            ".filter(b=>b.offsetParent!==null&&!b.disabled).map(b=>b.id))"
        )
        for bid in json.loads(buttons or "[]"):
            if bid in {"btnSettingsClose"}:
                continue
            before = await p.eval(STATUS_JS)
            try:
                await p.eval(f"document.getElementById({json.dumps(bid)}).click()")
            except RuntimeError as e:
                fails.append(f"{bid}: click threw {e}")
                continue
            await asyncio.sleep(1.2)
            after = await p.eval(STATUS_JS)
            bad = any(
                s in (after or "")
                for s in ("Load failed", "Failed to fetch", "undefined", "NetworkError", "500")
            )
            print(f"{'FAIL' if bad else 'ok  '} {bid}: {after if after != before else '(status unchanged)'}")
            if bad:
                fails.append(f"{bid}: {after}")
            # Close whatever the click opened so the next click is not covered.
            await p.eval(
                "(()=>{const c=document.getElementById('btnSettingsClose');if(c&&"
                "!document.getElementById('settingsPanel').classList.contains('hidden'))c.click();})()"
            )

        # Settings rows own rename/delete; exercise them on the throwaway project, which
        # also disposes of it.
        await p.eval("window.confirm = () => true")
        await p.eval("document.getElementById('btnSettings').click()")
        await asyncio.sleep(1.5)
        renamed = await p.eval(
            "(()=>{const r=document.querySelector(`.settings-proj-row[data-pid=\"%s\"]`);"
            "if(!r)return 'row missing';const i=r.querySelector('input');"
            "i.value='smoke-renamed';r.querySelectorAll('button')[0].click();return 'clicked';})()"
            % temp_pid
        )
        await asyncio.sleep(1.5)
        title_now = await p.eval(
            "(()=>{const o=[...document.getElementById('projectSelect').options]"
            ".find(o=>o.value==='%s');return o?o.textContent:'gone';})()" % temp_pid
        )
        print(f"rename: {renamed} -> {title_now}")
        if title_now != "smoke-renamed":
            fails.append(f"rename button did not take effect ({title_now})")
        await p.eval(
            "(()=>{const r=document.querySelector(`.settings-proj-row[data-pid=\"%s\"]`);"
            "if(r)r.querySelectorAll('button')[1].click();})()" % temp_pid
        )
        await asyncio.sleep(2.5)
        gone = await p.eval(
            "[...document.getElementById('projectSelect').options].every(o=>o.value!=='%s')"
            % temp_pid
        )
        print(f"delete: removed={gone}")
        if not gone:
            fails.append("delete button left the project in the list")
        await p.eval(
            "(()=>{const c=document.getElementById('btnSettingsClose');if(c)c.click();})()"
        )

        if console:
            print(f"console errors: {console}")

    print("----")
    if fails:
        for f in fails:
            print(f"FAIL {f}")
        print(f"UI_SMOKE_FAIL fails={len(fails)}")
        return 1
    print("UI_SMOKE_PASS fails=0")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--keep", action="store_true", help="leave Chrome open")
    ap.add_argument("--import-file", default=None, help="audio file to import via the UI")
    ap.add_argument(
        "--only-restore",
        action="store_true",
        help="only open a ☁ archived project and verify it comes back from iCloud",
    )
    args = ap.parse_args()
    if not Path(CHROME).exists():
        print("Google Chrome not installed — skipping UI smoke")
        return 0
    profile = tempfile.mkdtemp(prefix="xochi-uismoke-")
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            f"http://127.0.0.1:{args.port}/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        return asyncio.run(
            run(f"http://127.0.0.1:{args.port}/", args.import_file, args.only_restore)
        )
    finally:
        if not args.keep:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
