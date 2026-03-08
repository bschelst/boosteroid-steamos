#!/usr/bin/env python3
"""
Add Boosteroid as a non-Steam shortcut in Steam's library.

Author: Schelstraete Bart
        https://github.com/bschelst/boosteroid-steamos
        https://www.schelstraete.org
Reads and writes $STEAM_ROOT/userdata/<uid>/config/shortcuts.vdf
using binary VDF format. Idempotent — safe to run multiple times.
"""

import binascii
import glob
import os
import shutil
import struct
import sys

# vdf.py is installed alongside this script at /app/lib/boosteroid/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vdf  # noqa: E402  (vendored)

APP_NAME = "Boosteroid SteamOS"
# Full path required: Steam deletes shortcuts whose Exe is not an absolute path.
FLATPAK_EXE  = "/usr/bin/flatpak"
FLATPAK_ARGS = "run org.schelstraete.boosteroid"

# Compute the Steam shortcut artwork ID from exe+name (crc32 | 0x80000000).
# We write this into shortcuts.vdf so Steam uses exactly our value, which lets
# us install grid artwork under a known filename.
_APPID_UNSIGNED = (binascii.crc32((FLATPAK_EXE + APP_NAME).encode()) & 0xFFFFFFFF) | 0x80000000
# VDF binary format stores int32 as signed; convert for struct.pack compatibility.
_APPID_SIGNED = struct.unpack("<i", struct.pack("<I", _APPID_UNSIGNED))[0]

# /app/share is only visible inside the sandbox; Steam runs outside it.
# Steam does NOT support SVG shortcut icons — use the 256x256 PNG.
_SANDBOX_ICON = "/app/share/boosteroid/icon-256.png"
_USER_ICON_DIR = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
ICON_PATH = os.path.join(_USER_ICON_DIR, "org.schelstraete.boosteroid.png")


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
_CONTROLLER_CONFIGS = {
    "configset_controller_neptune.vdf": "/app/share/boosteroid/controller_config.vdf",
    "configset_controller_ps5.vdf":     "/app/share/boosteroid/controller_config_ps5.vdf",
}

# Steam Controller Configs are stored here (not in userdata).
# Non-Steam shortcuts use lowercase app name as the per-app directory key.
_STEAM_CTRL_CONFIGS_ROOTS = [
    os.path.expanduser("~/.local/share/Steam/steamapps/common/Steam Controller Configs"),
    os.path.expanduser("~/.steam/steam/steamapps/common/Steam Controller Configs"),
    os.path.expanduser("~/.var/app/com.valvesoftware.Steam/data/Steam/steamapps/common/Steam Controller Configs"),
]
_APP_KEY = APP_NAME.lower()  # "boosteroid steamos"


def _find_ctrl_config_dir(uid):
    for root in _STEAM_CTRL_CONFIGS_ROOTS:
        candidate = os.path.join(root, uid, "config")
        if os.path.isdir(candidate):
            return candidate
    # Dir doesn't exist yet — create it under the primary Steam path.
    primary = os.path.join(_STEAM_CTRL_CONFIGS_ROOTS[0], uid, "config")
    os.makedirs(primary, exist_ok=True)
    print(f"Created Steam Controller Configs dir: {primary}")
    return primary


def _update_configset(config_dir, configset_name, app_key):
    """Register our app in the given configset file with autosave=1."""
    configset_path = os.path.join(config_dir, configset_name)
    if not os.path.isfile(configset_path):
        return  # Controller type not present on this system — skip silently
    with open(configset_path, "r") as f:
        data = vdf.load(f, mapper=vdf.VDFDict)
    root = data.get("controller_config", data)
    if app_key not in root:
        root[app_key] = vdf.VDFDict({"autosave": "1"})
        with open(configset_path, "w") as f:
            vdf.dump(data, f, pretty=True)
        print(f"Registered '{app_key}' in {configset_name}")
    else:
        print(f"Controller configset entry already present in {configset_name}")


def _install_controller_config(shortcuts_vdf_path):
    """Install Steam Input controller layout (Mouse+KB default, L4 toggles Gamepad).

    Installs configs for Steam Deck (controller_neptune) and PS5 DualSense (controller_ps5).
    Files go in: steamapps/common/Steam Controller Configs/{uid}/config/{app_name_lower}/
    Each is registered in its configset with "autosave" "1".
    """
    uid = os.path.basename(os.path.dirname(shortcuts_vdf_path))

    # Remove stale file from the wrong location (old installs put it in userdata).
    old_dst = os.path.join(
        os.path.dirname(shortcuts_vdf_path), "controller_configs", "apps", f"{_APPID_UNSIGNED}.vdf"
    )
    if os.path.exists(old_dst):
        os.remove(old_dst)
        print(f"Removed stale controller config: {old_dst}")

    config_dir = _find_ctrl_config_dir(uid)
    if config_dir is None:
        print("Steam Controller Configs dir not found — skipping controller config", file=sys.stderr)
        return

    app_dir = os.path.join(config_dir, _APP_KEY)
    os.makedirs(app_dir, exist_ok=True)

    for configset_name, src in _CONTROLLER_CONFIGS.items():
        if not os.path.isfile(src):
            continue
        # Derive the per-controller filename from the configset name:
        #   configset_controller_neptune.vdf  →  controller_neptune.vdf
        ctrl_filename = configset_name.replace("configset_", "")
        dst = os.path.join(app_dir, ctrl_filename)
        with open(src, "r") as f:
            cfg = vdf.load(f, mapper=vdf.VDFDict)
        cfg["controller_mappings"]["export_type"] = "unknown"
        with open(dst, "w") as f:
            vdf.dump(cfg, f, pretty=True)
        os.utime(dst, None)
        print(f"Controller config installed: {dst}")
        _update_configset(config_dir, configset_name, _APP_KEY)


def _install_grid_images(shortcuts_vdf_path):
    """Copy Steam library artwork using the single known shortcut app ID."""
    grid_dst = os.path.join(os.path.dirname(shortcuts_vdf_path), "grid")
    os.makedirs(grid_dst, exist_ok=True)
    app_id = _APPID_UNSIGNED
    mappings = {
        "hero.png":    f"{app_id}_hero.png",
        "capsule.png": f"{app_id}p.png",
        "wide.png":    f"{app_id}.png",
        "logo.png":    f"{app_id}_logo.png",
    }
    print(f"Grid dir: {grid_dst}")
    for src_name, dst_name in mappings.items():
        src = os.path.join(_GRID_SRC, src_name)
        dst = os.path.join(grid_dst, dst_name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            os.utime(dst, None)  # Reset epoch-0 timestamps from Flatpak bundle
            print(f"Grid image installed: {dst}")
        else:
            print(f"Grid source missing: {src}", file=sys.stderr)


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

    # Remove any stale entries (wrong Exe from previous installs) and re-add cleanly.
    # Also covers the old bare "flatpak" exe that Steam removes on restart.
    stale_keys = [
        k for k, e in shortcuts.items()
        if e.get("AppName") == APP_NAME and e.get("Exe") != FLATPAK_EXE
    ]
    for k in stale_keys:
        print(f"Removing stale shortcut entry (wrong Exe): {shortcuts[k].get('Exe')!r}")
        del shortcuts[k]

    # Idempotency: only write shortcuts.vdf if the entry is missing or the appid
    # field needs to be added.  Grid images are always (re-)installed.
    correct_entry = next(
        (e for e in shortcuts.values()
         if e.get("AppName") == APP_NAME and e.get("Exe") == FLATPAK_EXE),
        None,
    )

    needs_write = False
    if correct_entry is None:
        # Create new entry with an explicit appid so Steam uses our known value.
        used = set(shortcuts.keys())
        idx = 0
        while str(idx) in used:
            idx += 1
        shortcuts[str(idx)] = vdf.VDFDict(
            {
                "appid": _APPID_SIGNED,
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
        needs_write = True
        print(f"Added '{APP_NAME}' to Steam library ({path}) — appid={_APPID_UNSIGNED}")
        print("Restart Steam to see it in your library.")
    elif correct_entry.get("appid") != _APPID_SIGNED or correct_entry.get("icon") != ICON_PATH:
        # Backfill missing/stale appid or wrong icon path (SVG → PNG migration).
        correct_entry["appid"] = _APPID_SIGNED
        correct_entry["icon"] = ICON_PATH
        needs_write = True
        print(f"Updated appid/icon on existing entry")
    else:
        print("Boosteroid shortcut already present and correct.")

    if needs_write:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            vdf.binary_dump(data, f)

    # Always install grid images — repairs missing artwork on every launch
    _install_grid_images(path)
    _install_controller_config(path)


if __name__ == "__main__":
    main()
