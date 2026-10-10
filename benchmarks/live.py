"""Opt-in, billable native browser and desktop fixture acceptance."""

import argparse
import json
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from apixly_jev_harness import AgentLoop, verify_state
from apixly_jev_harness.surfaces import browser_task, desktop_task

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run_browser(directory):
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(ROOT / "examples/fixtures"))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/form.html"
    task = browser_task(
        url=url,
        session="general",
        values={"traveler_name": "Mira"},
        verify=verify_state(
            text="Draft ready: Mira | London | flexible=true",
            controls=[
                {"label": "Traveler name", "value": "Mira"},
                {"label": "Destination", "value": "London"},
                {"label": "Flexible dates", "checked": True},
            ],
        ),
        authorize=lambda ctx, action: (
            action.params["arguments"]["target"]["label"] in ("Flexible dates", "Prepare draft")
        ),
    )
    try:
        result = AgentLoop().run(
            task,
            goal="First fill Traveler name with Mira. Next select London as Destination. Then enable Flexible dates. Finally click Prepare draft. Stop only when the draft ready result shows all three values.",
            max_steps=10,
            timeout_seconds=120,
            archive=directory / "browser.jsonl",
        )
        final = task.observe(None)
        import urllib.request

        screenshot_url = (
            task.surface.base + f"/tabs/{task.surface.tab}/screenshot?userId=camofox-general"
        )
        try:
            with urllib.request.urlopen(screenshot_url, timeout=10) as response:
                pixels = response.read()
            (directory / "browser.png").write_bytes(pixels)
        except Exception:
            result["screenshot_status"] = "unavailable"
        (directory / "browser-final.json").write_text(json.dumps(final, ensure_ascii=False))
        return result
    finally:
        task.surface.close()
        server.shutdown()
        server.server_close()


def run_desktop(directory):
    if sys.platform != "darwin":
        return {"status": "not_measured", "reason": "macos_fixture_only"}
    binary = directory / "jev-harness-desktop-fixture"
    subprocess.run(
        ["swiftc", str(ROOT / "examples/fixtures/DesktopFixture.swift"), "-o", str(binary)],
        check=True,
        capture_output=True,
    )
    process = subprocess.Popen([str(binary)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    task = None
    try:
        task = desktop_task(
            window="Jev Harness Desktop Fixture",
            process="jev-harness-desktop-fixture",
            values={"traveler_name": "Mira"},
            verify=lambda ctx, state: "Draft ready: Mira | flexible=true" in state["text"],
            authorize=lambda ctx, action: (
                action.params["arguments"]["target"]["label"] in ("Flexible dates", "Prepare draft")
            ),
        )
        result = AgentLoop().run(
            task,
            goal="Enter Mira as Traveler name, enable Flexible dates, and Prepare draft. Stop only when Draft ready: Mira | flexible=true is visible.",
            max_steps=8,
            timeout_seconds=120,
            archive=directory / "desktop.jsonl",
        )
        (directory / "desktop-final.json").write_text(
            json.dumps(task.observe(None), ensure_ascii=False)
        )
        return result
    finally:
        if task is not None:
            task.surface.backend.close()
        process.terminate()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--case", choices=["browser", "desktop", "both"], default="both")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "scope": "local synthetic fixtures; native Camofox and macOS Accessibility; not real bookings or production UI",
        "cases": {},
    }
    for name, fn in [("browser", run_browser), ("desktop", run_desktop)]:
        if args.case not in (name, "both"):
            continue
        try:
            result = fn(directory)
        except Exception as error:
            result = {
                "status": "failed",
                "complete": False,
                "error_type": type(error).__name__,
                "usage_complete": False,
            }
            receipt = directory / (name + ".jsonl")
            if receipt.exists():
                events = [json.loads(line) for line in receipt.read_text().splitlines()]
                if events[-1].get("event") == "terminal":
                    result = events[-1]["result"]
                    result["artifact_error_type"] = type(error).__name__
        if "archive" in result:
            result["archive"] = Path(result["archive"]).name
        report["cases"][name] = result
        print(json.dumps({"case": name, **result}, ensure_ascii=False))
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(r.get("complete") for r in report["cases"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
