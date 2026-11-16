"""Start the API and the dashboard in the background if they are not already running.

    python -m scripts.launcher            (from backend/)   start what is missing, then exit
    python -m scripts.launcher --status   print what is running

Used by the browser extension's native-messaging helper (browser-extension/native-host),
so opening Gemini, ChatGPT or Claude starts monitoring automatically. Servers run
hidden, detached from whatever started them, and log to backend/data/logs/.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
LOGS = BACKEND / "data" / "logs"
API_PORT, DASHBOARD_PORT = 8000, 5173

# Windows process flags: no console, own process group, and outside the browser's job
# object so the servers keep running after the helper exits.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def api_ready() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def _spawn(cmd: list, cwd: Path, log_name: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / log_name, "ab")
    if os.name != "nt":
        subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)
        return
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    try:
        subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, close_fds=True)
    except OSError:
        # The parent's job forbids breakaway: let Windows (WMI) start it as an independent process.
        # `cmd /s /c "..."` keeps the inner quotes (e.g. "C:\Program Files\...") intact.
        line = subprocess.list2cmdline(cmd) + f' >> "{LOGS / log_name}" 2>&1'
        command_line = f'cmd.exe /s /c "{line}"'.replace("'", "''")
        ps = ("$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0};"
              f"$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{"
              f"CommandLine='{command_line}'; CurrentDirectory='{cwd}'; ProcessStartupInformation=$si}};"
              "exit $r.ReturnValue")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           creationflags=CREATE_NO_WINDOW, timeout=30, capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(f"Could not start {log_name.split('.')[0]} (WMI code {r.returncode}): "
                               f"{r.stderr.decode(errors='replace')[:200]}")


def start_api() -> str:
    if port_open(API_PORT):
        return "running"
    _spawn([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
           BACKEND, "api.log")
    return "starting"


def start_dashboard() -> str:
    if port_open(DASHBOARD_PORT):
        return "running"
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite.exists():
        return "unavailable: run `npm install` in frontend/"
    _spawn([node, str(vite), "--port", str(DASHBOARD_PORT), "--strictPort"], FRONTEND, "dashboard.log")
    return "starting"


def ensure(wait_s: float = 0) -> dict:
    out = {"api": start_api(), "dashboard": start_dashboard()}
    deadline = time.time() + wait_s
    while wait_s and out["api"] == "starting" and time.time() < deadline:
        if api_ready():
            out["api"] = "running"
            break
        time.sleep(1)
    return out


def status() -> dict:
    return {"api": "running" if api_ready() else ("starting" if port_open(API_PORT) else "stopped"),
            "dashboard": "running" if port_open(DASHBOARD_PORT) else "stopped"}


if __name__ == "__main__":
    print(json.dumps(status() if "--status" in sys.argv else ensure(wait_s=60)))
