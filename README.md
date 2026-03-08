# ☁ Boosteroid for Steam Deck (unofficial)

[![Build Flatpak](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml/badge.svg)](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/bschelst/boosteroid-steamos)](https://github.com/bschelst/boosteroid-steamos/releases/latest)

[![Install](https://img.shields.io/badge/⬇_Install-Steam_Deck_%7C_Bazzite-1a9fff?style=for-the-badge)](https://github.com/bschelst/boosteroid-steamos/releases/latest/download/boosteroid-steamos.desktop)

> **Not affiliated with Boosteroid, Valve, or Steam.** See [Disclaimer](#%EF%B8%8F-disclaimer) below.

An **unofficial** Flatpak that brings Boosteroid cloud gaming to the Steam Deck — something Boosteroid has never officially provided despite the platform's popularity.

This project downloads and runs the **official, unmodified Boosteroid binary** from boosteroid.com. It only packages it into a Flatpak sandbox with the dependencies and configuration needed to run on SteamOS.

---

## ✅ Features

- **One-click install** from Desktop Mode via the included `.desktop` installer
- **First-run auto-setup**: downloads the official Boosteroid client on first launch — no manual steps
- **Steam library integration**: automatically adds Boosteroid as a shortcut in your Steam library
- **Hardware-accelerated video** on Steam Deck: AMD VA-API enabled automatically
- **Controllers & headsets**: full support for gamepads, USB and Bluetooth audio devices
- **Google login in Game Mode**: opens in Steam's browser without leaving Game Mode
- **Works in both modes**: Game Mode (Gamescope) and Desktop Mode (KDE Plasma)

---

## 🎮 Install on Steam Deck (recommended)

### Step 1 — Switch to Desktop Mode

Press **Steam button → Power → Switch to Desktop**.

### Step 2 — Download the installer

Click the **Install** button at the top of this page. The file `boosteroid-steamos.desktop` is saved to your **Downloads** folder.

### Step 3 — Run the installer

Open **Dolphin** (the file manager) and go to your **Downloads** folder.

Right-click `boosteroid-steamos.desktop` → **Allow Launching**, then **double-click** it.

A terminal window opens and installs everything automatically.

### Step 4 — Return to Game Mode

Once the installer finishes, press **Steam → Return to Gaming Mode**.

Boosteroid will be in your Steam library. **On first launch**, the official Boosteroid client (~120 MB) is downloaded automatically — this only happens once.

> **Note:** If Boosteroid doesn't appear in your library, restart Steam first: in Desktop Mode, click **Steam → Restart Steam**.

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

## 🕹️ Controller layout

A Steam Input layout is installed automatically on every launch. It has two modes — use **L5** (upper left grip) to switch between them at any time.

### Default mode — Mouse + Keyboard

Use this mode to navigate Boosteroid's menus and game browser.

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

### Grip buttons (available in both modes)

| Input | Action |
|---|---|
| **L4** (lower left grip) | Alt+R |
| **L5** (upper left grip) | Switch between Mouse+Keyboard ↔ Gamepad |
| **R5** (upper right grip) | Ctrl+F2 (Boosteroid streaming shortcut) |

> **Note:** The layout is reset on every launch. Any changes made via Steam → Controller Settings will be overwritten.

---

## ⚙️ Video decoder

On AMD (Steam Deck), VA-API hardware decode is selected automatically. You can override this:

```bash
flatpak run org.schelstraete.boosteroid           # auto (VA-API on AMD)
flatpak run org.schelstraete.boosteroid -vaapi    # force VA-API
flatpak run org.schelstraete.boosteroid -vdpau    # VDPAU (NVIDIA)
flatpak run org.schelstraete.boosteroid -cuda     # CUDA (NVIDIA with CUDA)
flatpak run org.schelstraete.boosteroid -s        # software decoder
```

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

## 🤔 Why this exists

Boosteroid offers a Linux `.deb` / AUR package, but getting it to run on Steam Deck has always been a mess:

- SteamOS has a **read-only filesystem** — you cannot install `.deb` or AUR packages the normal way
- The binary requires `libnuma.so.1`, a library missing from the Steam Deck environment
- There is no official Flatpak, no Snap, no AppImage — nothing that works out of the box
- Workarounds involve switching to Desktop Mode, installing third-party package managers, fighting with filesystem permissions, or running scripts blindly from the internet

The Steam Deck has existed since 2022. In over three years they have not shipped a package format that works on SteamOS. This project exists because they didn't.

---

## ⚠️ Disclaimer

This is an **unofficial community project** and is **not affiliated with, endorsed by, or connected to**:

- **Boosteroid** (Boosteroid Games S.R.L.) — the cloud gaming service
- **Valve Corporation** — makers of Steam and the Steam Deck
- Any other company or service mentioned in this repository

The Boosteroid name, logo, and service are trademarks of Boosteroid Games S.R.L. The Steam name, logo, and Steam Deck are trademarks of Valve Corporation. All trademarks belong to their respective owners.

Use of this project is at your own risk. The maintainer is not responsible for issues arising from use of the Boosteroid service itself.
