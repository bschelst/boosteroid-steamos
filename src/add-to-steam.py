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

APP_NAME = "Boosteroid SteamOS"
FLATPAK_EXE  = "flatpak"
FLATPAK_ARGS = "run org.schelstraete.boosteroid"

# /app/share is only visible inside the sandbox; Steam runs outside it.
# We copy the icon to the user's XDG icon theme so Steam can find it.
_SANDBOX_ICON = "/app/share/icons/hicolor/scalable/apps/org.schelstraete.boosteroid.svg"
_USER_ICON_DIR = os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps")
ICON_PATH = os.path.join(_USER_ICON_DIR, "org.schelstraete.boosteroid.svg")


def _install_icon():
    if not os.path.isfile(_SANDBOX_ICON):
        print(f"WARNING: sandbox icon not found at {_SANDBOX_ICON}", file=sys.stderr)
        return
    os.makedirs(_USER_ICON_DIR, exist_ok=True)
    shutil.copy2(_SANDBOX_ICON, ICON_PATH)
    print(f"Icon installed to {ICON_PATH}")


# Steam can live in multiple locations depending on how it is installed
STEAM_ROOTS = [
    os.path.expanduser("~/.local/share/Steam"),
    os.path.expanduser("~/.steam/steam"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/data/Steam"),
]


def find_shortcuts_vdf():
    """
    Return the path to shortcuts.vdf, even if it doesn't exist yet.
    Steam may not create it until the first non-Steam game is added via the UI,
    so we fall back to constructing the path from the userdata directory.
    """
    for root in STEAM_ROOTS:
        # Prefer an existing file
        pattern = os.path.join(root, "userdata", "*", "config", "shortcuts.vdf")
        matches = glob.glob(pattern)
        if matches:
            print(f"Found existing shortcuts.vdf: {matches[0]}")
            return matches[0]

        # File doesn't exist yet — find the userdata dir and build the path
        userdata_pattern = os.path.join(root, "userdata", "*")
        userdata_dirs = [d for d in glob.glob(userdata_pattern) if os.path.isdir(d)]
        if userdata_dirs:
            path = os.path.join(userdata_dirs[0], "config", "shortcuts.vdf")
            print(f"shortcuts.vdf not found, will create at: {path}")
            return path

    return None


_GRID_SRC = "/app/share/boosteroid/grid"

# Steam calculates the non-Steam shortcut artwork ID from exe+appname, but the
# exact formula varies (with/without quotes around exe).  Install artwork for
# all plausible IDs so Steam finds it regardless of which formula it uses.
def _all_possible_ids(exe, appname):
    import binascii
    candidates = [
        exe + appname,
        f'"{exe}"' + appname,
    ]
    return [binascii.crc32(k.encode()) & 0xFFFFFFFF | 0x80000000 for k in candidates]


def _install_grid_images(shortcuts_vdf_path):
    """Copy Steam library artwork for all possible shortcut IDs."""
    grid_dst = os.path.join(os.path.dirname(shortcuts_vdf_path), "grid")
    os.makedirs(grid_dst, exist_ok=True)
    for app_id in _all_possible_ids(FLATPAK_EXE, APP_NAME):
        mappings = {
            "hero.png":    f"{app_id}_hero.png",
            "capsule.png": f"{app_id}p.png",
            "wide.png":    f"{app_id}.png",
            "logo.png":    f"{app_id}_logo.png",
        }
        for src_name, dst_name in mappings.items():
            src = os.path.join(_GRID_SRC, src_name)
            dst = os.path.join(grid_dst, dst_name)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                print(f"Grid image installed: {dst_name}")


def main():
    _install_icon()
    path = find_shortcuts_vdf()
    if not path:
        print(
            "Steam userdata directory not found — skipping shortcut creation.\n"
            f"Searched: {STEAM_ROOTS}\n"
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

    # Remove any stale entries (wrong Exe from previous installs) and re-add cleanly
    stale_keys = [
        k for k, e in shortcuts.items()
        if e.get("AppName") == APP_NAME and e.get("Exe") != FLATPAK_EXE
    ]
    for k in stale_keys:
        print(f"Removing stale shortcut entry (wrong Exe): {shortcuts[k].get('Exe')!r}")
        del shortcuts[k]

    # Idempotency: only write shortcuts.vdf if the entry is missing or wrong.
    # Grid images are always (re-)installed regardless, so artwork repairs itself.
    already_correct = any(
        e.get("AppName") == APP_NAME and e.get("Exe") == FLATPAK_EXE
        for e in shortcuts.values()
    )

    if not already_correct:
        # Find the next unused numeric index
        used = set(shortcuts.keys())
        idx = 0
        while str(idx) in used:
            idx += 1
        index = str(idx)
        shortcuts[index] = vdf.VDFDict(
            {
                "AppName": APP_NAME,
                "Exe": FLATPAK_EXE,
                "StartDir": os.path.expanduser("~"),
                "icon": ICON_PATH,
                "ShortcutPath": "",
                "LaunchOptions": FLATPAK_ARGS,
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
    else:
        print("Boosteroid shortcut already present and correct.")

    # Always install grid images — repairs missing artwork on every launch
    _install_grid_images(path)


if __name__ == "__main__":
    main()
