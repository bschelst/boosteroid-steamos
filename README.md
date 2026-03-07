# Boosteroid for Steam Deck & Linux

Installs the [Boosteroid](https://boosteroid.com) cloud gaming client as a Flatpak on Steam Deck and desktop Linux.

On first launch, the Boosteroid client is downloaded from boosteroid.com, installed into your user data directory, and added to your Steam library as a non-Steam shortcut.

## Install

Download the latest `.flatpak` from [Releases](https://github.com/bschelst/boosteroid-steamos/releases), then:

```bash
flatpak install --user org.schelstraete.boosteroid.flatpak
flatpak run org.schelstraete.boosteroid
```

## Build from source

```bash
# Install runtime (once)
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08

# Build
flatpak-builder --user --force-clean build-dir org.schelstraete.boosteroid.yml

# Bundle
flatpak build-bundle ~/.local/share/flatpak/repo org.schelstraete.boosteroid.flatpak org.schelstraete.boosteroid

# Install locally
flatpak install --user org.schelstraete.boosteroid.flatpak
```

## Video decoder options

Pass flags when launching to select the decoder:

```bash
flatpak run org.schelstraete.boosteroid -vaapi   # VA-API (recommended on AMD/Intel)
flatpak run org.schelstraete.boosteroid -vdpau   # VDPAU (NVIDIA)
flatpak run org.schelstraete.boosteroid -s        # software decoder
```

## Notes

- x86_64 only (Boosteroid's client is 64-bit only)
- On first launch, ~120 MB is downloaded from boosteroid.com
- Restart Steam after first launch to see the shortcut in Game Mode
