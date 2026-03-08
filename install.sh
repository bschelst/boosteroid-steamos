#!/bin/bash
# One-click installer for Boosteroid (unofficial) Flatpak on Steam Deck / SteamOS.
# Usage: bash install.sh
#
# Author: Schelstraete Bart
#         https://github.com/bschelst/boosteroid-steamos
#         https://www.schelstraete.org
set -euo pipefail

FLATPAK_URL="https://github.com/bschelst/boosteroid-steamos/releases/latest/download/org.schelstraete.boosteroid.flatpak"
FLATHUB_REPO="https://flathub.org/repo/flathub.flatpakrepo"
TMP_FLATPAK="$(mktemp /tmp/boosteroid-XXXXXX.flatpak)"

# Detect release version via the redirect Location header (no download needed).
RELEASE_TAG=$(curl -fsI "$FLATPAK_URL" 2>/dev/null \
    | grep -i '^location:' \
    | sed 's|.*/download/\([^/]*\)/.*|\1|' \
    | tr -d '\r\n') || RELEASE_TAG=""

_PROG_PIPE=""
cleanup() { rm -f "$TMP_FLATPAK" "${_PROG_PIPE:-}"; }
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
printf "${B}  ║${R}    ${B}☁${R}  ${M}☁${R}                                  ${P}☁${R}  ${P}☁${R}            ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${W}${BOLD}  B  O  O  S  T  E  R  O  I  D  ${R}                      ${B}║${R}\n"
printf "${B}  ║${R}    ${M}  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ${R}                   ${B}║${R}\n"
printf "${B}  ║${R}    ${P}  ( u n o f f i c i a l )          ${R}                   ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}Cloud Gaming · Steam Deck Flatpak Installer${R}           ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${P}  ╚══════════════════════════════════════════════════════════╝${R}\n"
printf "\n"

# ── Install steps ─────────────────────────────────────────────────────────────
step() { printf "${Y}  ==> ${W}${BOLD}%s${R}\n" "$1"; }
ok()   { printf "${G}  ✓   %s${R}\n" "$1"; }

step "Ensuring Flathub remote is configured..."
flatpak remote-add --user --if-not-exists flathub "$FLATHUB_REPO"
ok "Flathub ready"

step "Downloading Boosteroid Flatpak${RELEASE_TAG:+ (${RELEASE_TAG})}..."
# Indent the progress bar to match the 2-space prefix used by step()/ok().
# curl --progress-bar writes \r-delimited updates to stderr; awk splits on \r
# and re-emits each update preceded by "\r  " so the bar is visually aligned.
# Named FIFO + explicit wait ensures "Download complete" prints only after the
# final bar line is flushed (process-substitution timing is not reliable here).
_PROG_PIPE=$(mktemp -u /tmp/.boosteroid-dl-XXXXXX)
mkfifo "$_PROG_PIPE"
awk 'BEGIN{RS="\r";ORS=""}{printf "\r  %s",$0;fflush()}' < "$_PROG_PIPE" >&2 &
_PROG_PID=$!
curl -L --progress-bar -o "$TMP_FLATPAK" "$FLATPAK_URL" 2>"$_PROG_PIPE"
wait "$_PROG_PID" 2>/dev/null || true
printf "\n" >&2
rm -f "$_PROG_PIPE"; _PROG_PIPE=""
ok "Download complete"

step "Installing (this may take a minute on first run)..."
if ! FLATPAK_OUT=$(TERM=dumb flatpak install --user -y "$TMP_FLATPAK" 2>&1); then
    printf "%s\n" "$FLATPAK_OUT"
    exit 1
fi
ok "Flatpak installed${RELEASE_TAG:+ — ${RELEASE_TAG}}"

step "Adding Boosteroid to your Steam library..."
flatpak run --command=python3 org.schelstraete.boosteroid \
    /app/lib/boosteroid/add-to-steam.py 2>&1 \
    | sed 's/^/      /' \
    && ok "Steam shortcut added" \
    || printf "${Y}  !   Could not add Steam shortcut automatically.\n${R}      Add manually: flatpak run org.schelstraete.boosteroid\n"

printf "\n"
printf "${B}  ╔══════════════════════════════════════════════════════════╗${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${G}${BOLD}✓  Done!${R}                                              ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    Switch to ${W}Game Mode${R} — Boosteroid is in your library.  ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}On first launch: ~120 MB downloaded from              ${B}║${R}\n"
printf "${B}  ║${R}    ${DIM}boosteroid.com.                                       ${B}║${R}\n"
printf "${B}  ║${R}                                                          ${B}║${R}\n"
printf "${P}  ╚══════════════════════════════════════════════════════════╝${R}\n"
printf "\n"

read -r -t 15 -p "  Press Enter to close (auto-closes in 15s)..." || true
printf "\n"
