#!/bin/bash
# One-click installer for Boosteroid (unofficial) Flatpak on Steam Deck / SteamOS.
# Usage: bash install.sh
set -euo pipefail

FLATPAK_URL="https://github.com/bschelst/boosteroid-steamos/releases/latest/download/org.schelstraete.boosteroid.flatpak"
FLATHUB_REPO="https://flathub.org/repo/flathub.flatpakrepo"
TMP_FLATPAK="$(mktemp /tmp/boosteroid-XXXXXX.flatpak)"

cleanup() { rm -f "$TMP_FLATPAK"; }
trap cleanup EXIT

echo "================================================"
echo "  Boosteroid (unofficial) — Flatpak Installer"
echo "================================================"
echo ""

echo "==> Ensuring Flathub remote is configured..."
flatpak remote-add --user --if-not-exists flathub "$FLATHUB_REPO"

echo "==> Downloading Boosteroid Flatpak..."
curl -L --progress-bar -o "$TMP_FLATPAK" "$FLATPAK_URL"

echo "==> Installing (this may take a minute on first run)..."
flatpak install --user -y "$TMP_FLATPAK"

echo ""
echo "================================================"
echo "  Done!"
echo "  Launch 'Boosteroid (unofficial)' from your"
echo "  app menu or Steam library."
echo ""
echo "  On first launch it will download the"
echo "  Boosteroid client (~150 MB)."
echo "================================================"
