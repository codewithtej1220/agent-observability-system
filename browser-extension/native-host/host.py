"""Native-messaging helper: lets the extension start the local API and dashboard.

Edge/Chrome start this program when the extension calls
chrome.runtime.sendNativeMessage("com.aobs.launcher", {cmd: "ensure" | "status"}).
It answers with {"api": ..., "dashboard": ...} and exits. Messages are a 4-byte
little-endian length followed by UTF-8 JSON, on stdin/stdout.

Register it once with:  python browser-extension/native-host/install.py
"""
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from scripts import launcher  # noqa: E402


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (n,) = struct.unpack("<I", raw)
    return json.loads(sys.stdin.buffer.read(n) or b"{}")


def write_message(obj) -> None:
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def main() -> None:
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    msg = read_message() or {}
    try:
        result = launcher.status() if msg.get("cmd") == "status" else launcher.ensure()
        write_message({"ok": True, **result})
    except Exception as e:  # noqa: BLE001  (always answer, never hang the browser)
        write_message({"ok": False, "error": f"{type(e).__name__}: {e}"[:300]})


if __name__ == "__main__":
    main()
