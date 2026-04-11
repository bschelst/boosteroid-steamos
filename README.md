# ☁ Boosteroid for Steam OS & Bazzite (unofficial)

[![Build Flatpak](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml/badge.svg)](https://github.com/bschelst/boosteroid-steamos/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/bschelst/boosteroid-steamos)](https://github.com/bschelst/boosteroid-steamos/releases/latest)

[![Install](https://img.shields.io/badge/⬇_Install-Steam_Deck_%7C_Bazzite-1a9fff?style=for-the-badge)](https://github.com/bschelst/boosteroid-steamos/releases/latest/download/boosteroid-steamos.desktop)

> **Not affiliated with Boosteroid, Valve, or Steam.** See [Disclaimer](#%EF%B8%8F-disclaimer) below.

An **unofficial** Flatpak that brings native Boosteroid cloud gaming to SteamOS (Steam Deck) and Bazzite — something Boosteroid has never officially provided despite the platform's popularity.

This project downloads and runs the **official, unmodified native Boosteroid binary** from boosteroid.com. It only packages it into a Flatpak sandbox with the dependencies and configuration needed to run on SteamOS/Bazzite.

---

## ✅ Features

- **One-click install** from Desktop Mode via the included `.desktop` installer
- **First-run auto-setup**: downloads the official Boosteroid client on first launch — no manual steps
- **Steam library integration**: automatically adds Boosteroid as a shortcut with controller layout and grid artwork
- **Hardware-accelerated video** on Steam Deck: AMD VA-API enabled automatically
- **H.264 / H.265 codec forcing** via opt-in env vars for cleaner visuals at the same bitrate
- **Auto-scaling splash screen** that adapts to handheld (1280×800), docked 1080p, 1440p, and 4K displays
- **Boosteroid gateway status monitoring** via an independent status page (see below)
- **Controllers & headsets**: full support for gamepads, USB and Bluetooth audio devices
- **Google login in Game Mode**: opens in Steam's browser without leaving Game Mode
- **Works in both modes**: Game Mode (Gamescope) and Desktop Mode (KDE Plasma)
- **Video clips**: recordings saved by Boosteroid are stored in `~/Videos/BoosteroidClips`

## 🤔 Why this exists

Boosteroid offers a Linux `.deb` / AUR package, but getting it to run on Steam Deck has always been a mess:

- SteamOS has a **read-only filesystem** — you cannot install `.deb` or AUR packages the normal way
- The binary requires `libnuma.so.1`, a library missing from the Steam Deck environment
- There is no official Flatpak, no Snap, no AppImage — nothing that works out of the box
- Workarounds involve switching to Desktop Mode, installing third-party package managers, fighting with filesystem permissions, routing through a browser, or running scripts blindly from the internet

The Steam Deck has existed since 2022. In over three years Boosteroid has not shipped a package format that works on SteamOS. This project exists because they didn't.

## 🎮 Install on Steam Deck & Bazzite (recommended)

### 🖥️ Step 1 — Switch to Desktop Mode

Press **Steam button → Power → Switch to Desktop**.

### ⬇️ Step 2 — Download the installer

Click the **Install** button at the top of this page. The file `boosteroid-steamos.desktop` is saved to your **Downloads** folder.

### ▶️ Step 3 — Run the installer

Open **Dolphin** (the file manager) and go to your **Downloads** folder.

Double click `boosteroid-steamos.desktop` → **Launch** → **Continue**.

A terminal window opens and installs everything automatically.

### 🕹️ Step 4 — Return to Game Mode

Once the installer finishes, press **Steam → Return to Gaming Mode**.

Look for **Boosteroid SteamOS** in your Steam library. **On first launch**, the official Boosteroid client (~120 MB) is downloaded automatically — this only happens once.

> **Note:** If Boosteroid SteamOS doesn't appear in your library, restart Steam first.

## 🖥️ Manual install

If you prefer to install without the `.desktop` installer:

```bash
# Download the Flatpak bundle from the latest release
curl -L -O https://github.com/bschelst/boosteroid-steamos/releases/latest/download/org.schelstraete.boosteroid.flatpak

# Install
flatpak install --user ./org.schelstraete.boosteroid.flatpak
```

## 🕹️ Controller layout

A Steam Input layout is installed automatically on every launch with two modes you can switch at any time. Expand the sections below for full button mappings.

<details>
<summary><strong>Steam Deck — default mode (Mouse + Keyboard)</strong></summary>

| Input | Action |
|---|---|
| Right trackpad | Mouse cursor |
| Right trackpad click | Left click |
| Right trackpad double-tap | Switch to Gamepad mode |
| Left stick | Mouse movement |
| D-pad | Arrow keys / scroll |
| **A** | Left click |
| **B** | Right click |
| **X** | Space |
| **Y** | Escape |
| Left trigger | Left click |
| Right trigger | Right click |
| LB / RB | Page Up / Page Down |
| Start (☰) | Escape |
| Select (⧉) | Tab |
| **L4** (lower left grip) | Alt+R (Boosteroid shortcut) |
| **L5** (upper left grip) | Switch Mouse+Keyboard ↔ Gamepad |
| **R5** (upper right grip) | Ctrl+F2 (stream shortcut) |

**Gamepad mode** — full xinput passthrough; all buttons, sticks and triggers sent directly to the game. Switch back with **L5** or right trackpad double-tap.

</details>

<details>
<summary><strong>PS5 DualSense — default mode (Mouse + Keyboard)</strong></summary>

| Input | Action |
|---|---|
| Touchpad | Mouse cursor (absolute) |
| Touchpad click | Left click |
| Touchpad double-tap | Switch to Gamepad mode |
| Left stick | Mouse movement |
| D-pad | Arrow keys |
| **Cross** | Left click |
| **Circle** | Right click |
| **Square** | Space |
| **Triangle** | Escape |
| Left trigger | Left click |
| Right trigger | Right click |
| L1 / R1 | Page Up / Page Down |
| Options | Escape — long-press = Ctrl+F2 — double-press = Alt+R |
| Create | Tab — long-press = Switch Mouse+Keyboard ↔ Gamepad |

**Gamepad mode** — full xinput passthrough; all buttons, sticks and triggers sent directly to the game.

</details>

> **Note:** The layout is installed only if not already present — any customizations you make in Steam are preserved. To reset to defaults, delete `~/.local/share/Steam/steamapps/common/Steam Controller Configs/*/config/boosteroid steamos/controller_*.vdf` and restart Steam.

## ⚙️ Configuration

All optional settings are controlled via Steam **Launch Options** (Steam → Library → Boosteroid SteamOS → ⚙ Manage → Edit launch options) or persistently via `flatpak override`.

### 🐛 Debug mode

By default, `[debug]` lines from the Boosteroid client are stripped from `~/logs/boosteroid.log` to keep it readable. Enable full debug output:

```
run --env=DEBUG=1 org.schelstraete.boosteroid
```

### 🚫 Disable splash screen

Skip the loading splash entirely:

```
run --env=NOSPLASH=1 org.schelstraete.boosteroid
```

Combine multiple env vars in one line:

```
run --env=DEBUG=1 --env=NOSPLASH=1 org.schelstraete.boosteroid
```

### 🎛️ Video decoder

On AMD (Steam Deck), VA-API hardware decode is selected automatically. You can override this:

```bash
flatpak run org.schelstraete.boosteroid           # auto (VA-API on AMD)
flatpak run org.schelstraete.boosteroid -vaapi    # force VA-API
flatpak run org.schelstraete.boosteroid -vdpau    # VDPAU (NVIDIA)
flatpak run org.schelstraete.boosteroid -cuda     # CUDA (NVIDIA with CUDA)
flatpak run org.schelstraete.boosteroid -s        # software decoder
```

See also **[Force codec](#%EF%B8%8F-force-codec-h264--h265--experimental)** below for controlling *which codec* the server sends, independent of how the client decodes it.

### 🎞️ Force codec (H.264 / H.265) — experimental

The Boosteroid Linux client tends to default to **H.264** even on hardware that can decode HEVC. The Steam Deck APU (AMD VCN 3.0) has full hardware HEVC decode, so forcing H.265 can deliver cleaner visuals at the same bitrate.

Two opt-in environment variables are honored by the launcher:

| Env var | Effect |
|---|---|
| `BOOSTEROID_FORCE_H265=1` | Pass `-h265` to the Boosteroid binary (force HEVC) |
| `BOOSTEROID_FORCE_H264=1` | Pass `-h264` to the Boosteroid binary (force H.264) |

Set via Steam **Launch Options**:

```
run --env=BOOSTEROID_FORCE_H265=1 org.schelstraete.boosteroid
```

Or persistently with `flatpak override` (applies to every launch, including from Steam):

```bash
flatpak override --user --env=BOOSTEROID_FORCE_H265=1 org.schelstraete.boosteroid
flatpak override --user --reset org.schelstraete.boosteroid    # back to defaults
```

After launching a stream, check what was actually negotiated:

```bash
grep -E "H265 codec/parser opened|H264 codec/parser opened" ~/logs/boosteroid.log
```

- **Two `codec/parser opened` lines** (one `H264` + one `H265`) — the stream is running H.265
- **One line only** (`H264`) — the stream is running H.264 (the H.264 parser is used for both the startup probe and the stream, so no second line appears)

> **Note:** These flags are undocumented by Boosteroid and were discovered by inspecting the binary. They may stop working in a future Boosteroid client update.

## 📡 Boosteroid service status

If your stream drops, freezes, or has high latency, it's often a gateway-side problem rather than anything on your Deck. The unofficial **Boosteroid Service Status** page continuously probes Boosteroid's streaming gateways (EU, US, APAC) and reports which regions are up, degraded, or offline — along with the last 7 days of incidents.

[![Service Status](https://img.shields.io/badge/📡_Check_Status-boosteroid.schelstraete.org-1a9fff?style=for-the-badge)](https://boosteroid.schelstraete.org/status)

Check it when:

- A stream won't connect or drops immediately after launch
- Latency spikes or stuttering appears out of nowhere
- The in-app network test shows all servers as unreachable (see [Help & troubleshooting](#-help--troubleshooting) below)

> **Note:** This status page is run independently by the maintainer of this project and is **not** an official Boosteroid service. It exists because Boosteroid has no public status page of their own.

## 🩹 Help & troubleshooting

**The in-app network test reports all servers as unreachable**

This is a Flatpak sandbox limitation — ICMP ping requires elevated privileges not available in user-mode Flatpak builds. **Actual game streaming is unaffected.** If you want to verify the Boosteroid gateways are actually up, use the [service status page](#-boosteroid-service-status) instead.

**Boosteroid doesn't appear in Game Mode library after first launch**

Restart Steam from Desktop Mode (`steam -shutdown && steam`) or reboot.

**Google login doesn't open a browser in Game Mode**

This should work automatically via Steam's built-in browser. If it doesn't, log in from Desktop Mode first — the session persists when you switch back to Game Mode.

**Black screen or no video after logging in**

First, check the [service status page](#-boosteroid-service-status) to rule out a gateway outage. If Boosteroid's gateways are up, try forcing the software decoder:

```bash
flatpak run org.schelstraete.boosteroid -s
```

**Controller not detected**

Make sure you launch Boosteroid SteamOS from Steam (not directly from the app menu) so it runs under the Steam Input layer.

## 🔨 Build from source

```bash
# Add Flathub and install the runtime (once)
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08

# Build
flatpak-builder --user --force-clean build-dir org.schelstraete.boosteroid.yml

# Bundle
flatpak build-bundle ~/.local/share/flatpak/repo \
    org.schelstraete.boosteroid.flatpak \
    org.schelstraete.boosteroid

# Install locally
flatpak install --user ./org.schelstraete.boosteroid.flatpak
```

## 🗑️ Uninstall

```bash
flatpak uninstall --user org.schelstraete.boosteroid
```

To also remove the downloaded Boosteroid client:

```bash
rm -rf ~/.var/app/org.schelstraete.boosteroid
```

## ⚠️ Disclaimer

This is an **unofficial community project** and is **not affiliated with, endorsed by, or connected to**:

- **Boosteroid** (Boosteroid Games S.R.L.) — the cloud gaming service
- **Valve Corporation** — makers of Steam and the Steam Deck
- Any other company or service mentioned in this repository

The Boosteroid name, logo, and service are trademarks of Boosteroid Games S.R.L. The Steam name, logo, and Steam Deck are trademarks of Valve Corporation. All trademarks belong to their respective owners.

Use of this project is at your own risk. The maintainer is not responsible for issues arising from use of the Boosteroid service itself.
