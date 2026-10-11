"""Create labeled screenshot-replay media from the unchanged local browser fixture.

Requires the named headless Camofox service, ffmpeg and cwebp. No model calls, bookings,
credentials, or customer data are used. Only the tab created here is closed.
"""

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples/fixtures/form.html"
OUT = ROOT / "web/media"
DURATIONS = [1.5, 1.8, 1.8, 1.8, 1.5, 3.6]
COPY = {
    "en": {
        "title": "A goal becomes a verified draft.",
        "replay": "SCREENSHOT REPLAY / NO NEW INFERENCE",
        "goal_label": "THE TASK",
        "goal": "Mira. London. Flexible dates.<br>Prepare the draft, then check the result.",
        "flow": "A bounded browser task",
        "caption": "Current screenshots of the v0.1.0 fixture sequence. Not a recorded Jev run.",
        "fixture": "LOCAL SYNTHETIC FIXTURE · NO REAL BOOKING OR MESSAGE",
        "steps": [
            "Observe",
            "Fill name",
            "Select destination",
            "Enable flexibility",
            "Prepare draft",
            "Verify outcome",
        ],
        "headings": [
            "Read the current controls",
            "Bind the supplied name",
            "Choose an observed option",
            "Apply the requested toggle",
            "Prepare the local draft",
            "Check fields and final text",
        ],
        "details": [
            "The program observes the page before each step.",
            "fill → Traveler name → Mira",
            "select → Destination → London",
            "click → Flexible dates → checked",
            "click → Prepare draft",
            "Name + destination + toggle + result all match.",
        ],
        "result": "Independent check passed",
        "pending": "Awaiting final verification",
        "done": "VERIFIED",
        "initial": "CURRENT STATE",
        "left": "The code supplies the controls,<br>arguments and completion check.",
    },
    "zh-CN": {
        "title": "从一个目标，到验证完成的草稿。",
        "replay": "界面截图回放 / 无新增推理",
        "goal_label": "本次任务",
        "goal": "Mira，伦敦，灵活日期。<br>准备草稿后，核对最终结果。",
        "flow": "有边界的浏览器任务",
        "caption": "当前界面截图，回放 v0.1.0 夹具步骤；不是 Jev 推理录屏。",
        "fixture": "本地合成夹具 · 不会创建真实预订或发送消息",
        "steps": ["观察现场", "填写姓名", "选择目的地", "启用灵活日期", "准备草稿", "验证结果"],
        "headings": [
            "读取当前可操作控件",
            "绑定程序提供的姓名",
            "选择现场已有的选项",
            "勾选要求的日期偏好",
            "准备本地草稿",
            "核对控件与最终文本",
        ],
        "details": [
            "程序在每一步之前重新观察页面。",
            "fill → Traveler name → Mira",
            "select → Destination → London",
            "click → Flexible dates → checked",
            "click → Prepare draft",
            "姓名、目的地、开关和结果文本全部一致。",
        ],
        "result": "独立验证通过",
        "pending": "等待最终结果验证",
        "done": "已验证",
        "initial": "当前状态",
        "left": "程序提供可用控件、参数<br>以及独立的完成条件。",
    },
}


def stage(language):
    copy = COPY[language]
    steps = "".join(
        f'<div class="step" id="step-{index}"><span>{index + 1:02}</span><b>{html.escape(label)}</b><i>●</i></div>'
        for index, label in enumerate(copy["steps"])
    )
    return f'''<!doctype html><html lang="{language}"><meta charset="utf-8"><title>Jev Harness screenshot replay</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#080b0f;color:#edf2f4;font:16px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;width:1280px;height:720px;overflow:hidden}}
.canvas{{position:relative;width:1280px;height:720px;padding:30px 44px;background:radial-gradient(ellipse at 80% 10%,#18313399,transparent 53%),radial-gradient(ellipse at 0% 100%,#25341966,transparent 42%),#080b0f}}
header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px}}.brand{{font-size:21px;font-weight:700;letter-spacing:-.6px}}.brand span{{font-weight:400;color:#8a9a9d}}.tag{{font:11px ui-monospace,Menlo,monospace;color:#c6f67a;letter-spacing:1.3px;border:1px solid #b7df7333;padding:8px 11px;border-radius:6px}}
h1{{font-size:33px;line-height:1.2;letter-spacing:-1px;margin:0 0 23px;font-weight:650}}.layout{{display:grid;grid-template-columns:326px 1fr;gap:24px;height:488px}}
.sidebar{{display:flex;flex-direction:column}}.label{{font:10px ui-monospace,Menlo,monospace;letter-spacing:2px;color:#7de3e5;margin-bottom:9px}}.goal{{font-size:18px;line-height:1.55;color:#e9eff0;margin-bottom:18px}}
.flow-title{{color:#8f9d9f;font-size:12px;margin-bottom:13px}}.steps{{display:grid;gap:8px}}.step{{height:39px;display:flex;align-items:center;padding:0 11px;border:1px solid #233137;border-radius:7px;background:#10181c;color:#677d82;gap:13px}}.step span{{font:11px ui-monospace,monospace}}.step b{{font-size:13px;font-weight:500}}.step i{{font-style:normal;font-size:10px;margin-left:auto;color:#2b4148}}.step.active{{color:#c6f67a;border-color:#b6df7266;background:#1c261c}}.step.active i{{color:#c6f67a}}.step.done{{color:#98aca8}}.step.done i{{color:#729d82}}
.note{{font-size:13px;line-height:1.5;color:#7d949b;margin-top:auto}}.browser{{position:relative;border:1px solid #35464c;border-radius:12px;overflow:hidden;background:#12191d;box-shadow:0 24px 80px #0006}}.chrome{{height:39px;border-bottom:1px solid #344249;background:#172025;display:flex;gap:5px;align-items:center;padding:0 16px}}.dot{{width:7px;height:7px;background:#5c6d71;border-radius:50%}}.chrome small{{font:10px ui-monospace,monospace;color:#849a9f;margin-left:14px;letter-spacing:1px}}
.fixture{{height:362px;overflow:hidden;background:#f3f5fa}}iframe{{border:0;width:1120px;height:650px;transform:scale(.75);transform-origin:top left;display:block;pointer-events:none}}
.readout{{height:87px;padding:15px 20px;background:#10191e;border-top:1px solid #2b4148;display:flex;align-items:center;justify-content:space-between;gap:15px}}.readout h2{{margin:0 0 7px;font-size:17px;letter-spacing:-.4px;font-weight:600}}.readout p{{margin:0;color:#7de3e5;font:11px ui-monospace,monospace;line-height:1.5}}.state{{flex-shrink:0;font:10px ui-monospace,monospace;padding:8px 9px;border:1px solid #334c57;border-radius:5px;color:#849da7}}.state.verified{{color:#c6f67a;border-color:#a5d36277;background:#c6f67a0d}}
footer{{margin-top:24px;display:flex;justify-content:space-between;gap:20px;font-size:11px;color:#738991;line-height:1.5}}footer strong{{font:10px ui-monospace,monospace;color:#93a6a5;letter-spacing:.5px}}
</style><main class="canvas"><header><div class="brand">jev <span>/ harness</span></div><div class="tag">{copy["replay"]}</div></header><h1>{copy["title"]}</h1>
<div class="layout"><aside class="sidebar"><div class="label">{copy["goal_label"]}</div><div class="goal">{copy["goal"]}</div><div class="flow-title">{copy["flow"]}</div><div class="steps">{steps}</div><div class="note">{copy["left"]}</div></aside><div class="browser"><div class="chrome"><span class="dot"></span><span class="dot"></span><span class="dot"></span><small>examples/fixtures/form.html</small></div><div class="fixture"><iframe src="/form.html" title="Unchanged local synthetic form fixture"></iframe></div><div class="readout"><div><h2 id="heading"></h2><p id="detail"></p></div><div class="state" id="state">{copy["initial"]}</div></div></div></div><footer><span>{copy["caption"]}</span><strong>{copy["fixture"]}</strong></footer></main>
</html>'''


def api(base, method, path, data=None, binary=False):
    headers = {"Content-Type": "application/json"}
    if os.environ.get("CAMOFOX_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["CAMOFOX_API_KEY"]
    request = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read() if binary else json.load(response)


def evaluate(base, tab, user, expression):
    reply = api(base, "POST", f"/tabs/{tab}/evaluate", {"userId": user, "expression": expression})
    if reply.get("ok") is False:
        raise RuntimeError("replay_evaluation_failed")
    return reply.get("result")


def encode(frames, destination, suffix):
    timeline = frames / "timeline.txt"
    timeline.write_text(
        "".join(
            f"file '{index:02}.png'\nduration {duration}\n"
            for index, duration in enumerate(DURATIONS)
        )
        + "file '05.png'\n"
    )
    common = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(
        common
        + [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(timeline),
            "-t",
            "12",
            "-vf",
            "fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination / f"browser-demo{suffix}.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "cwebp",
            "-quiet",
            "-q",
            "85",
            str(frames / "05.png"),
            "-o",
            str(destination / f"browser-poster{suffix}.webp"),
        ],
        check=True,
    )
    subprocess.run(
        common
        + [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(timeline),
            "-t",
            "12",
            "-filter_complex",
            "fps=5,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
            "-loop",
            "0",
            str(destination / f"browser-demo{suffix}.gif"),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="general")
    parser.add_argument("--base", default="http://127.0.0.1:9378")
    args = parser.parse_args()
    if os.environ.get("CAMOFOX_INTERACTIVE", "off") != "off":
        raise SystemExit("Headless Camofox is required: CAMOFOX_INTERACTIVE=off")
    if urllib.parse.urlsplit(args.base).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("The Camofox service must be local")
    if not all(shutil.which(tool) for tool in ("ffmpeg", "cwebp")):
        raise SystemExit("ffmpeg and cwebp are required")
    subprocess.run(
        ["camofox", "--session", args.session, "health"], check=True, capture_output=True
    )
    OUT.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/form.html":
                body = FIXTURE.read_bytes()
            elif parsed.path == "/stage.html":
                language = urllib.parse.parse_qs(parsed.query).get("lang", ["en"])[0]
                body = stage(language if language in COPY else "en").encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    user, tab = "camofox-" + args.session, None
    expected = "Draft ready: Mira | London | flexible=true"
    verification = {}
    try:
        local = f"http://127.0.0.1:{server.server_port}/stage.html"
        tab = api(
            args.base, "POST", "/tabs", {"userId": user, "sessionKey": args.session, "url": local}
        )["tabId"]
        api(
            args.base,
            "POST",
            f"/tabs/{tab}/viewport",
            {"userId": user, "width": 1280, "height": 720},
        )
        with tempfile.TemporaryDirectory(prefix="harness-showcase-") as temp:
            for language in COPY:
                suffix = "" if language == "en" else ".zh-CN"
                api(
                    args.base,
                    "POST",
                    f"/tabs/{tab}/navigate",
                    {"userId": user, "url": local + "?lang=" + language},
                )
                deadline = time.monotonic() + 15
                ready = "document.querySelector('iframe')?.contentDocument?.querySelector('#name') !== null && !!document.querySelector('iframe')?.contentDocument?.querySelector('#name')"
                while not evaluate(args.base, tab, user, ready):
                    if time.monotonic() > deadline:
                        raise RuntimeError("fixture_load_timeout")
                    time.sleep(0.05)
                frames = Path(temp) / language
                frames.mkdir()
                for index in range(6):
                    operation = {
                        0: "",
                        1: "doc.querySelector('#name').value='Mira';",
                        2: "doc.querySelector('#destination').value='London';",
                        3: "doc.querySelector('#flexible').click();",
                        4: "doc.querySelector('#apply').click();",
                        5: "",
                    }[index]
                    copy = COPY[language]
                    update = (
                        f"document.querySelectorAll('.step').forEach((node,i)=>{{node.classList.toggle('active',i==={index});node.classList.toggle('done',i<{index})}});"
                        f"document.querySelector('#heading').textContent={json.dumps(copy['headings'][index])};"
                        f"document.querySelector('#detail').textContent={json.dumps(copy['details'][index])};"
                        f"document.querySelector('#state').textContent={json.dumps(copy['done'] if index == 5 else copy['initial'])};"
                        f"document.querySelector('#state').classList.toggle('verified',{str(index == 5).lower()});"
                    )
                    evaluate(
                        args.base,
                        tab,
                        user,
                        f"(()=>{{const doc=document.querySelector('iframe').contentDocument;{operation}{update}return true}})()",
                    )
                    pixels = api(
                        args.base, "GET", f"/tabs/{tab}/screenshot?userId={user}", binary=True
                    )
                    (frames / f"{index:02}.png").write_bytes(pixels)
                final = evaluate(
                    args.base,
                    tab,
                    user,
                    "(()=>{const d=document.querySelector('iframe').contentDocument;return {name:d.querySelector('#name').value,destination:d.querySelector('#destination').value,flexible:d.querySelector('#flexible').checked,result:d.querySelector('#result').textContent}})()",
                )
                if final != {
                    "name": "Mira",
                    "destination": "London",
                    "flexible": True,
                    "result": expected,
                }:
                    raise RuntimeError("independent_fixture_verification_failed")
                verification[language] = final
                encode(frames, OUT, suffix)
    finally:
        if tab:
            api(args.base, "DELETE", f"/tabs/{tab}", {"userId": user})
        server.shutdown()
        server.server_close()
    files = {
        file.name: {
            "bytes": file.stat().st_size,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
        for file in sorted(OUT.glob("browser-*"))
        if file.suffix in (".mp4", ".gif", ".webp")
    }
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "illustrative_screenshot_replay",
        "capture": "headless Camofox, current unchanged local synthetic form fixture",
        "inference_calls": 0,
        "historical_evidence": "reports/acceptance.json; live browser evidence belongs to v0.1.0",
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "duration_seconds": sum(DURATIONS),
        "video_pixels": [1280, 720],
        "real_bookings_or_messages": 0,
        "verification": verification,
        "files": files,
    }
    (OUT / "showcase.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"kind": manifest["kind"], "files": files}, indent=2))


if __name__ == "__main__":
    main()
