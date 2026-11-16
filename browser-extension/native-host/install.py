"""Register the native-messaging helper for this user (no admin rights needed).

    python browser-extension/native-host/install.py [EXTENSION_ID ...]
    python browser-extension/native-host/install.py --uninstall

Writes com.aobs.launcher.json next to this file and points Edge and Chrome at it
(HKCU\\Software\\Microsoft\\Edge|Google\\Chrome\\NativeMessagingHosts). Only the given
extension IDs may use it. Without IDs, the IDs of this unpacked extension are read
from the Edge and Chrome profiles (only the entry whose path is this folder).
"""
import glob
import json
import os
import sys
from pathlib import Path

NAME = "com.aobs.launcher"
HERE = Path(__file__).resolve().parent
EXT_DIR = HERE.parent
REG_KEYS = [r"Software\Microsoft\Edge\NativeMessagingHosts", r"Software\Google\Chrome\NativeMessagingHosts"]
PROFILE_ROOTS = [r"%LOCALAPPDATA%\Microsoft\Edge\User Data", r"%LOCALAPPDATA%\Google\Chrome\User Data"]


def installed_ids() -> set:
    """IDs under which browsers loaded this folder as an unpacked extension."""
    ids = set()
    target = os.path.normcase(str(EXT_DIR))
    for root in PROFILE_ROOTS:
        for f in glob.glob(os.path.join(os.path.expandvars(root), "*", "*Preferences")):
            try:
                settings = json.load(open(f, encoding="utf-8")).get("extensions", {}).get("settings", {})
            except (OSError, ValueError):
                continue
            for ext_id, s in settings.items():
                if isinstance(s, dict) and os.path.normcase(s.get("path", "")) == target:
                    ids.add(ext_id)
    return ids


def install(ids) -> None:
    import winreg

    cmd = HERE / "host.cmd"
    cmd.write_text(f'@echo off\r\n"{sys.executable}" -u "{HERE / "host.py"}" %*\r\n', encoding="utf-8")
    manifest = HERE / f"{NAME}.json"
    manifest.write_text(json.dumps({
        "name": NAME,
        "description": "Agent Observability: starts the local API and dashboard for the chat monitor",
        "path": str(cmd),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{i}/" for i in sorted(ids)],
    }, indent=2), encoding="utf-8")
    for key in REG_KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key}\\{NAME}") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest))
    print(f"Registered {NAME} for extension(s): {', '.join(sorted(ids))}")
    print(f"Manifest: {manifest}")


def uninstall() -> None:
    import winreg

    for key in REG_KEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{key}\\{NAME}")
        except FileNotFoundError:
            pass
    print(f"Unregistered {NAME}")


if __name__ == "__main__":
    if os.name != "nt":
        sys.exit("This installer is for Windows.")
    if "--uninstall" in sys.argv:
        uninstall()
    else:
        ids = set(a for a in sys.argv[1:] if not a.startswith("-")) or installed_ids()
        if not ids:
            sys.exit("Load the extension in Edge or Chrome first (Load unpacked), then run this again.")
        install(ids)
