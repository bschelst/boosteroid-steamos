#!/bin/bash
# One-click installer for Boosteroid (unofficial) Flatpak on Steam Deck / SteamOS.
# Usage: bash install.sh
set -euo pipefail

FLATPAK_URL="https://github.com/bschelst/boosteroid-steamos/releases/latest/download/org.schelstraete.boosteroid.flatpak"
FLATHUB_REPO="https://flathub.org/repo/flathub.flatpakrepo"
TMP_FLATPAK="$(mktemp /tmp/boosteroid-XXXXXX.flatpak)"

cleanup() { rm -f "$TMP_FLATPAK"; }
trap cleanup EXIT

# ── ANSI colours ─────────────────────────────────────────────────────────────
R=$'\033[0m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
B=$'\033[38;5;33m'    # blue  (#2096D9 approx)
M=$'\033[38;5;63m'    # blue-purple
P=$'\033[38;5;99m'    # purple (#5C35EE approx)
W=$'\033[1;97m'       # bright white
G=$'\033[38;5;82m'    # green (success)
Y=$'\033[38;5;220m'   # yellow (warning/step)

# ── Banner ───────────────────────────────────────────────────────────────────
printf "\n"
printf "${B}  ╔══════════════════════════════════════════════════════════╗${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${B}☁${R}  ${M}☁${R}                                  ${P}☁${R}  ${P}☁${R}         ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${W}${BOLD}  B  O  O  S  T  E  R  O  I  D  ${R}                    ${B}║${R}\n"
printf "${B}  ║${R}    ${M}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ${R}                    ${B}║${R}\n"
printf "${B}  ║${R}    ${P}  ( u n o f f i c i a l )          ${R}                    ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}Cloud Gaming · Steam Deck Flatpak Installer${R}            ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${P}  ╚══════════════════════════════════════════════════════════╝${R}\n"
printf "\n"

# ── Install steps ─────────────────────────────────────────────────────────────
step() { printf "${Y}  ==> ${W}${BOLD}%s${R}\n" "$1"; }
ok()   { printf "${G}  ✓   %s${R}\n" "$1"; }

step "Ensuring Flathub remote is configured..."
flatpak remote-add --user --if-not-exists flathub "$FLATHUB_REPO"
ok "Flathub ready"

step "Downloading Boosteroid Flatpak..."
curl -L --progress-bar -o "$TMP_FLATPAK" "$FLATPAK_URL"
ok "Download complete"

step "Installing (this may take a minute on first run)..."
flatpak install --user -y "$TMP_FLATPAK"
ok "Flatpak installed"

# Steam must NOT be running when we write shortcuts.vdf — if it is, it will
# overwrite the file with its in-memory copy when it closes, erasing our entry.
step "Stopping Steam so the library update is not overwritten..."
steam -shutdown 2>/dev/null || true
# Wait up to 8 s for Steam to actually exit
for i in $(seq 1 8); do
    pgrep -x steam >/dev/null 2>&1 || break
    sleep 1
done
ok "Steam stopped"

step "Adding Boosteroid to your Steam library..."
flatpak run --command=python3 org.schelstraete.boosteroid \
    /app/lib/boosteroid/add-to-steam.py \
    && ok "Steam shortcut added" \
    || printf "${Y}  !   Could not add Steam shortcut automatically.\n${R}      Add manually: flatpak run org.schelstraete.boosteroid\n"

printf "\n"
printf "${B}  ╔══════════════════════════════════════════════════════════╗${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${G}${BOLD}✓  Done!${R}                                            ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    Switch to ${W}Game Mode${R} — Boosteroid is in your library. ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}On first launch: ~120 MB downloaded from              ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}boosteroid.com.                                        ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${P}  ╚══════════════════════════════════════════════════════════╝${R}\n"
printf "\n"

read -r -t 15 -p "  Press Enter to close (auto-closes in 15s)..." || true
printf "\n"
