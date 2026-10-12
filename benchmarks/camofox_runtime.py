"""Read-only runtime evidence for one Camofox named session.

Service configuration (environment, plist, launcher arguments) only says what the
service was asked to do; it is never accepted as runtime proof here. A passing
packet needs all of:

* service health listing the named session's full-profile context as active;
* the OS process table: every browser process launched under the service listener
  carries ``-headless`` (the session's own profile process must be among them when
  the service version's profile naming is known) and the process tree owns no
  visible top-level window where windows are observable;
* a pointer-trajectory probe on a controller-owned page, opened in its own tab of
  the same session and clicked through the same Camofox click route that actions
  use: humanized cursor movement yields many intermediate ``mousemove`` events,
  while a non-humanized move yields one.

Nothing here changes service configuration, restarts a service or closes a tab
that this module did not create. Probe thresholds are conservative lower bounds.
"""

import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_PROBE_MOVES = 8
MIN_PROBE_SPAN_MS = 100

PROBE_PAGE = b"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Pointer probe</title></head><body style="margin:0">
<div style="height:360px"></div>
<button id="pointer-probe" style="margin-left:560px;width:180px;height:64px">Probe</button>
<script>
const moves=[],clicks=[];
document.addEventListener('mousemove',e=>{moves.push([Math.round(performance.now()),e.clientX,e.clientY]);document.body.dataset.moves=JSON.stringify(moves)});
document.getElementById('pointer-probe').addEventListener('click',e=>{clicks.push([Math.round(performance.now()),e.clientX,e.clientY]);document.body.dataset.clicks=JSON.stringify(clicks)});
</script></body></html>"""


def service_health(base, *, opener=None):
    opener = opener or urllib.request.urlopen
    with opener(base.rstrip("/") + "/health", timeout=5) as response:
        return json.load(response)


def profile_directory_name(user, *, platform=None, service_version=None):
    """camofox-browser 2.4.x default-profile naming; None for unknown service versions."""
    if not isinstance(service_version, str) or not service_version.startswith("2.4."):
        return None
    platform = platform or sys.platform
    if platform == "win32":
        key = "u:" + base64.urlsafe_b64encode(user.encode("utf-16-le")).decode().rstrip("=")
        return "profile-" + hashlib.sha256(key.encode()).hexdigest()
    return urllib.parse.quote(user, safe="-_.!~*'()")


def listener_pid(port):
    """PID owning a loopback TCP listener, read from the OS; None when unobservable."""
    try:
        if os.name == "nt":
            output = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-NetTCPConnection -LocalPort {int(port)} -State Listen).OwningProcess",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout
        else:
            output = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=20,
            ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    values = {int(x) for x in output.split() if x.strip().isdigit()}
    return values.pop() if len(values) == 1 else None


def process_table():
    """[{pid, ppid, name, argv}] from the OS process table; [] when unobservable."""
    try:
        if os.name == "nt":
            script = (
                "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
                "Name,CommandLine | ConvertTo-Json -Depth 2 -Compress"
            )
            output = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            ).stdout
            rows = json.loads(output) if output.strip() else []
            rows = rows if isinstance(rows, list) else [rows]
            return [
                {
                    "pid": row["ProcessId"],
                    "ppid": row["ParentProcessId"],
                    "name": row.get("Name") or "",
                    "argv": _windows_argv(row.get("CommandLine") or ""),
                }
                for row in rows
            ]
        output = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    rows = []
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            argv = shlex.split(parts[2], posix=True) if parts[2] else []
            rows.append(
                {
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "name": os.path.basename(argv[0]) if argv else "",
                    "argv": argv,
                }
            )
    return rows


def _windows_argv(command_line):
    if not command_line:
        return []
    import ctypes
    from ctypes import wintypes

    count = ctypes.c_int()
    shell32 = ctypes.WinDLL("shell32")
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    shell32.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    pointer = shell32.CommandLineToArgvW(command_line, ctypes.byref(count))
    if not pointer:
        return command_line.split()
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(pointer)


def visible_window_pids(pids):
    """PIDs among ``pids`` owning a visible top-level window; None if unobservable."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = set()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(hwnd):
            found.add(owner.value)
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return found


def _descendants(rows, root):
    children = {}
    for row in rows:
        children.setdefault(row["ppid"], []).append(row)
    found, queue = [], [root]
    while queue:
        for row in children.get(queue.pop(), []):
            if row["pid"] not in {x["pid"] for x in found}:
                found.append(row)
                queue.append(row["pid"])
    return found


def _profile(argv):
    for index, value in enumerate(argv[:-1]):
        if value == "-profile":
            return argv[index + 1]
    return None


def headless_evidence(base, user, *, service_version=None, pid_of=None, rows=None, windows=None):
    """Browser-process launch arguments and visible windows for one service listener."""
    port = urllib.parse.urlsplit(base).port
    pid = (pid_of or listener_pid)(port)
    table = process_table() if rows is None else rows
    tree = _descendants(table, pid) if pid is not None else []
    # Browser instances are launched with a profile; content processes are not.
    browsers = [row for row in tree if _profile(row["argv"]) is not None]
    expected = profile_directory_name(user, service_version=service_version)
    session = [
        row
        for row in browsers
        if expected is not None
        and os.path.basename(_profile(row["argv"]).rstrip("/\\").replace("\\", "/")) == expected
    ]
    observed = (windows or visible_window_pids)({row["pid"] for row in tree}) if tree else None
    all_headless = bool(browsers) and all("-headless" in row["argv"] for row in browsers)
    problems = []
    if pid is None:
        problems.append("service_listener_unobserved")
    if not browsers:
        problems.append("browser_process_unobserved")
    elif not all_headless:
        problems.append("browser_process_not_headless")
    if expected is not None and not session:
        problems.append("session_profile_process_unobserved")
    if observed:
        problems.append("visible_browser_window")
    return {
        "kind": "os_process_table",
        "passed": not problems,
        "problems": problems,
        "service_listener_pid_observed": pid is not None,
        "browser_processes": len(browsers),
        "process_tree": len(tree),
        "all_browser_processes_headless": all_headless,
        "session_mapping": "profile_directory_match"
        if expected is not None
        else "unverified_all_service_browsers",
        "session_profile_process": bool(session),
        "visible_windows": None if observed is None else len(observed),
    }


class _ProbeServer:
    def __init__(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(PROBE_PAGE)))
                self.end_headers()
                self.wfile.write(PROBE_PAGE)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def trajectory_verdict(moves):
    distinct = len({(row[1], row[2]) for row in moves})
    span = moves[-1][0] - moves[0][0] if moves else 0
    return {
        "kind": "pointer_trajectory_probe",
        "moves": len(moves),
        "distinct_positions": distinct,
        "span_ms": span,
        "passed": len(moves) >= MIN_PROBE_MOVES
        and distinct >= MIN_PROBE_MOVES
        and span >= MIN_PROBE_SPAN_MS,
        "thresholds": {"moves": MIN_PROBE_MOVES, "span_ms": MIN_PROBE_SPAN_MS},
    }


def runtime_evidence(base, session, *, page_factory=None, health=None, headless=None):
    """Open one owned probe tab in ``session``, gather evidence, close only that tab."""
    if page_factory is None:
        from jev_context.act.browser import CamofoxPage

        page_factory = CamofoxPage
    health = health or service_health
    started = time.perf_counter()
    problems, page = [], None
    packet = {"service": None, "context": None, "headless": None, "humanize": None}
    with _ProbeServer() as probe:
        try:
            page = page_factory(session, url=probe.url, base=base)
            current = health(base)
            user = getattr(page, "user", "camofox-" + session)
            packet["service"] = {
                key: current.get(key) for key in ("ok", "engine", "version", "poolSize")
            }
            active = user in (current.get("activeUserIds") or [])
            packet["context"] = {
                "user_active": active,
                "browser_connected": current.get("browserConnected"),
            }
            if not active:
                problems.append("session_context_not_active")
            packet["headless"] = (headless or headless_evidence)(
                base, user, service_version=current.get("version")
            )
            problems += packet["headless"]["problems"]
            page._tab("click", {"selector": "#pointer-probe"})
            time.sleep(0.3)
            raw = page.evaluate("document.body.dataset.moves || '[]'")
            moves = json.loads(raw) if isinstance(raw, str) else []
            packet["humanize"] = trajectory_verdict(moves)
            if not packet["humanize"]["passed"]:
                problems.append("humanized_pointer_not_observed")
        except Exception as error:
            problems.append("runtime_probe_failed:" + type(error).__name__)
        finally:
            if page is not None and getattr(page, "owned", False):
                page.close()
    return {
        **packet,
        "passed": not problems,
        "problems": problems,
        "probe_tab_owned_and_closed": page is not None and getattr(page, "owned", False),
        "seconds": time.perf_counter() - started,
        "scope": "runtime observation; configuration is recorded separately and never proof",
    }


def await_session_ready(base, user, *, timeout_seconds=60, opener=None, sleep=time.sleep):
    """Wait while the named session's context has no tabs but is still tearing down.

    Camofox closes a full-profile context after its last tab closes; creating a tab in
    that window fails inside the service. Reads only health and the session's tab
    list, never closes or changes anything, and reports the wait instead of hiding it.
    """
    opener = opener or urllib.request.urlopen
    started = time.monotonic()
    while True:
        health = service_health(base, opener=opener)
        active = user in (health.get("activeUserIds") or [])
        query = urllib.parse.urlencode({"userId": user})
        with opener(base.rstrip("/") + "/tabs?" + query, timeout=5) as response:
            tabs = json.load(response).get("tabs") or []
        if not active or tabs:
            return {
                "context_active": active,
                "existing_tabs": len(tabs),
                "waited_seconds": round(time.monotonic() - started, 3),
            }
        if time.monotonic() - started >= timeout_seconds:
            raise RuntimeError("camofox_session_teardown_not_settled")
        sleep(0.25)
