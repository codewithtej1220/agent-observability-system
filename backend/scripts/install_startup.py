"""Start the API and dashboard automatically when you sign in to Windows.

    python -m scripts.install_startup            (from backend/)  add the startup shortcut
    python -m scripts.install_startup --remove   remove it

Adds "Agent Observability.lnk" to your Startup folder (shell:startup, this user only,
no admin rights). At sign-in it runs scripts.launcher with pythonw (no window), which
starts whatever is not already running. Logs go to backend/data/logs/.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
NAME = "Agent Observability.lnk"


def startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def install() -> Path:
    link = startup_dir() / NAME
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:AOBS_LINK);"
        "$s.TargetPath = $env:AOBS_TARGET; $s.Arguments = '-m scripts.launcher';"
        "$s.WorkingDirectory = $env:AOBS_CWD; $s.WindowStyle = 7;"
        "$s.Description = 'Starts the Agent Observability API and dashboard'; $s.Save()"
    )
    env = {**os.environ, "AOBS_LINK": str(link), "AOBS_TARGET": str(pythonw()), "AOBS_CWD": str(BACKEND)}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], check=True, env=env)
    return link


def remove() -> bool:
    link = startup_dir() / NAME
    if link.exists():
        link.unlink()
        return True
    return False


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("This installer is for Windows.")
    if "--remove" in sys.argv:
        print("Removed the startup shortcut." if remove() else "No startup shortcut was installed.")
    else:
        print(f"Installed: {install()}")
        print("The API and dashboard will start in the background each time you sign in to Windows.")
