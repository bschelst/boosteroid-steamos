#!/usr/bin/env python3
"""
Add Boosteroid as a non-Steam shortcut in Steam's library.
Reads and writes $STEAM_ROOT/userdata/<uid>/config/shortcuts.vdf
using binary VDF format. Idempotent — safe to run multiple times.
"""

import glob
import os
import shutil
import sys

# vdf.py is installed alongside this script at /app/lib/boosteroid/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vdf  # noqa: E402  (vendored)

APP_NAME = "Boosteroid"
FLATPAK_CMD = "flatpak run org.schelstraete.boosteroid"

# /app/share is only visible inside the sandbox; Steam runs outside it.
# We copy the icon to the user's XDG icon theme so Steam can find it.
_SANDBOX_ICON = "/app/share/icons/hicolor/scalable/apps/org.schelstraete.boosteroid.svg"
_USER_ICON_DIR = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")
ICON_PATH = os.path.join(_USER_ICON_DIR, "org.schelstraete.boosteroid.svg")


def _install_icon():
    if not os.path.isfile(_SANDBOX_ICON):
        return
    os.makedirs(_USER_ICON_DIR, exist_ok=True)
    shutil.copy2(_SANDBOX_ICON, ICON_PATH)

# Steam can live in multiple locations depending on how it is installed
STEAM_ROOTS = [
    os.path.expanduser("~/.local/share/Steam"),
    os.path.expanduser("~/.steam/steam"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/data/Steam"),
]


def find_shortcuts_vdf():
    for root in STEAM_ROOTS:
        pattern = os.path.join(root, "userdata", "*", "config", "shortcuts.vdf")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def main():
    _install_icon()
    path = find_shortcuts_vdf()
    if not path:
        print(
            "Steam userdata not found — skipping shortcut creation.\n"
            "You can manually add 'flatpak run org.schelstraete.boosteroid' as a non-Steam game.",
            file=sys.stderr,
        )
        return

    if os.path.exists(path):
        with open(path, "rb") as f:
            data = vdf.binary_load(f)
    else:
        data = vdf.VDFDict({"shortcuts": vdf.VDFDict()})

    shortcuts = data.setdefault("shortcuts", vdf.VDFDict())

    # Idempotency: skip if already present
    for entry in shortcuts.values():
        if entry.get("AppName") == APP_NAME or entry.get("Exe") == FLATPAK_CMD:
            print("Boosteroid shortcut already present in Steam library.")
            return

    # Find the next unused numeric index (Steam may use sparse non-sequential keys)
    used = set(shortcuts.keys())
    idx = 0
    while str(idx) in used:
        idx += 1
    index = str(idx)
    shortcuts[index] = vdf.VDFDict(
        {
            "AppName": APP_NAME,
            "Exe": FLATPAK_CMD,
            "StartDir": os.path.expanduser("~"),
            "icon": ICON_PATH,
            "ShortcutPath": "",
            "LaunchOptions": "",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "LastPlayTime": 0,
            "tags": vdf.VDFDict(),
        }
    )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        vdf.binary_dump(data, f)

    print(f"Added '{APP_NAME}' to Steam library ({path})")
    print("Restart Steam to see it in your library.")


if __name__ == "__main__":
    main()
