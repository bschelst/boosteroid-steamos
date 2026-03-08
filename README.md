# ☁ Boosteroid for Steam Deck (unofficial)

[![Build Flatpak](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml/badge.svg)](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/bschelst/boosteroid-steamos)](https://github.com/bschelst/boosteroid-steamos/releases/latest)

[![Install](https://img.shields.io/badge/⬇_Install-Steam_Deck_%7C_Bazzite-1a9fff?style=for-the-badge)](https://github.com/bschelst/boosteroid-steamos/releases/latest/download/boosteroid-steamos.desktop)

> **Not affiliated with Boosteroid, Valve, or Steam.** See [Disclaimer](#%EF%B8%8F-disclaimer) below.

An **unofficial** Flatpak package that makes Boosteroid cloud gaming work properly on Steam Deck and SteamOS — something Boosteroid themselves have failed to provide despite having no native client available on Steam Deck.

This project downloads and runs the **official, unmodified Boosteroid binary** from boosteroid.com. It does nothing more than package it into a Flatpak sandbox with all the dependencies and configuration needed to run on SteamOS.

---

## 🤦 Why this exists

Boosteroid offers a Linux `.deb` / AUR package, but getting it to run on Steam Deck has always been a mess:

- SteamOS has a **read-only filesystem** — you cannot install `.deb` packages the normal way
- The binary requires `libnuma.so.1`, a library missing from the Steam Deck environment
- There is no official Flatpak, no Snap, no AppImage — nothing that works out of the box
- Workarounds involve switching to Desktop Mode, installing third-party package managers, fighting with filesystem permissions, or running scripts blindly from Reddit posts

The Steam Deck has existed since 2022. In over three years they have not shipped a package format that works on SteamOS. This project exists because they didn't.

---

## ✅ Features

- **One-click install** from Desktop Mode via the included `.desktop` installer
- **First-run auto-setup**: downloads the official Boosteroid client on first launch — no manual steps
- **Steam library integration**: automatically adds Boosteroid as a non-Steam game shortcut
- **Hardware video decode** on AMD (Steam Deck): VA-API enabled automatically via the `radeonsi` driver
- **Controllers & headsets**: full `/dev/input/*` access for gamepads, USB and Bluetooth audio devices
- **Google login in Game Mode**: OAuth URLs route through Steam's built-in browser via Gamescope
- **Audio**: PulseAudio socket with PipeWire compatibility layer
- **Wayland + X11**: works under Gamescope (Game Mode) and KDE Plasma (Desktop Mode)

---

## 🎮 Install on Steam Deck (recommended)

### Step 1 — Switch to Desktop Mode

Press **Steam button → Power → Switch to Desktop**.

### Step 2 — Download the installer

Open a browser and go to the [latest release](https://github.com/bschelst/boosteroid-steamos/releases/latest). Download **`boosteroid-steamos.desktop`**.

### Step 3 — Run the installer

In Dolphin (file manager), navigate to where you saved the file. **Right-click → Allow Launching**, then **double-click** it.

A terminal window opens with a progress display and installs everything automatically.

### Step 4 — First launch

Open **Boosteroid (unofficial)** from the app menu or switch back to Game Mode and find it in your Steam library.

On first launch (~30 seconds), the official Boosteroid client is downloaded from boosteroid.com and installed into your user data directory. This only happens once.

> **Tip:** Restart Steam after first launch to see the Boosteroid shortcut appear in your Game Mode library.

---

## 🖥️ Manual install

If you prefer to install without the `.desktop` installer:

```bash
# Download the Flatpak bundle from the latest release
curl -L -O https://github.com/bschelst/boosteroid-steamos/releases/latest/download/org.schelstraete.boosteroid.flatpak

# Install
flatpak install --user ./org.schelstraete.boosteroid.flatpak
```

---

## ▶ Decoder options

On AMD (Steam Deck), VA-API hardware decode is selected automatically. You can override this manually:

```bash
flatpak run org.schelstraete.boosteroid           # auto (VA-API on AMD)
flatpak run org.schelstraete.boosteroid -vaapi    # force VA-API
flatpak run org.schelstraete.boosteroid -vdpau    # VDPAU (NVIDIA)
flatpak run org.schelstraete.boosteroid -cuda     # CUDA (NVIDIA with CUDA)
flatpak run org.schelstraete.boosteroid -s        # software decoder
```

---

## 🎮 Controller layout

A Steam Input layout is installed automatically on every launch. It has two modes you can switch between at any time.

### Default mode — Mouse + Keyboard

| Input | Action |
|---|---|
| Right trackpad | Mouse cursor |
| Right trackpad click | Left click |
| Right trackpad double-tap | Switch to Gamepad mode |
| Left stick | Mouse movement |
| Left stick click | Left click |
| **A** | Left click |
| **B** | Right click |
| **X** | Space |
| **Y** | Escape |
| D-pad | Arrow keys |
| Left trigger | Left click |
| Right trigger | Right click |
| LB | Page Up |
| RB | Page Down |
| Start | Escape |
| Select | Tab |

### Gamepad mode

Full xinput gamepad passthrough — all buttons, sticks and triggers are passed straight through to the game.

### Grip buttons (both modes)

| Input | Action |
|---|---|
| **L4** (lower left grip) | Alt+R |
| **L5** (upper left grip) | Switch between Mouse+Keyboard ↔ Gamepad |
| **R5** (upper right grip) | Ctrl+F2 (Boosteroid layout shortcut, active during streaming) |

> **Note:** The layout is updated on every launch. Any changes made via Steam → Controller Settings will be overwritten on the next launch.

---

## 🗑️ Uninstall

```bash
flatpak uninstall --user org.schelstraete.boosteroid
```

To also remove the downloaded Boosteroid client:

```bash
rm -rf ~/.var/app/org.schelstraete.boosteroid
```

---

## 🔨 Build from source

```bash
# Add Flathub and install the runtime (once)
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08

# Build
flatpak-builder --user --force-clean build-dir org.schelstraete.boosteroid.yml

# Bundle
flatpak build-bundle ~/.local/share/flatpak/repo \
    org.schelstraete.boosteroid.flatpak \
    org.schelstraete.boosteroid

# Install locally
flatpak install --user ./org.schelstraete.boosteroid.flatpak
```

---

## ⚠️ Known issues

- **Network test fails** — the in-app network test reports all servers as unreachable. This is a Flatpak sandbox limitation (ICMP ping requires elevated privileges not available in user-mode builds). Actual game streaming is unaffected.

---

## 🩹 Troubleshooting

**Boosteroid doesn't appear in Game Mode library after first launch**
Restart Steam from Desktop Mode (`steam -shutdown && steam`) or reboot.

**Google login doesn't open a browser in Game Mode**
This should work automatically via Steam's built-in browser. If it doesn't, log in from Desktop Mode first — the session persists when you switch back to Game Mode.

**Black screen or no video after logging in**
Try forcing the software decoder:
```bash
flatpak run org.schelstraete.boosteroid -s
```

**Controller not detected**
Make sure you launch Boosteroid from Steam (not directly from the app menu) so it runs under the Steam Input layer.

---

## 📝 Notes

- **x86\_64 only** — the official Boosteroid client is 64-bit only
- **~120 MB** downloaded from boosteroid.com on first launch
- The downloaded binary is the **official, unmodified Boosteroid client** — this project only packages it

---

## ⚠️ Disclaimer

This is an **unofficial community project** and is **not affiliated with, endorsed by, or connected to**:

- **Boosteroid** (Boosteroid Games S.R.L.) — the cloud gaming service
- **Valve Corporation** — makers of Steam and the Steam Deck
- Any other company or service mentioned in this repository

The Boosteroid name, logo, and service are trademarks of Boosteroid Games S.R.L. The Steam name, logo, and Steam Deck are trademarks of Valve Corporation. All trademarks belong to their respective owners.

Use of this project is at your own risk. The maintainer is not responsible for issues arising from use of the Boosteroid service itself.
