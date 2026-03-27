#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.
#
# Author: Schelstraete Bart
#         https://github.com/bschelst/boosteroid-steamos
#         https://www.schelstraete.org

set -euo pipefail

# Shared with splash screen for live status updates.
# Lifecycle: absent (no Boosteroid) → "step:/warn:" (waiting for old instance)
#            → "boosteroid_running" (Boosteroid is active) → absent on exit.
# The next launcher checks this file first before resorting to pgrep.
# Do NOT blindly rm -f here — the file may be a valid running indicator
# from the previous session.  Staleness is handled in _wait_for_boosteroid_close.
STATUS_FILE="/tmp/.boosteroid_splash_status"

# Ignore SIGTERM during startup so Steam session cleanup cannot kill this
# launcher while it is still in the wait-for-previous-instance loop.
# Default SIGTERM handling is restored just before Boosteroid is launched.
trap 'echo "==> Startup: SIGTERM received, continuing"' TERM

# ── Debug log (check ~/logs/boosteroid.log from Desktop Mode after launch) ───
mkdir -p "$HOME/logs"
mkdir -p "$HOME/Videos/BoosteroidClips"
LOG=$HOME/logs/boosteroid.log
> "$LOG"
exec > >(tee -a "$LOG") 2>&1
VERSION=$(cat /app/share/boosteroid/version 2>/dev/null || echo "unknown")
echo "=== Boosteroid $VERSION launch $(date) ==="
echo "DISPLAY=${DISPLAY:-<unset>}  WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-<unset>}"
echo "GAMESCOPE_WAYLAND_DISPLAY=${GAMESCOPE_WAYLAND_DISPLAY:-<unset>}"
echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-<unset>}"

# ── Splash screen ────────────────────────────────────────────────────────────
# Show a loading splash early so the user sees something immediately.
# Requires a display (X11 or Wayland); silently skipped if neither is available.
# To disable, add --env=NOSPLASH=1 to Steam launch options:
#   run --env=NOSPLASH=1 org.schelstraete.boosteroid
SPLASH_PID=""
if [ "${NOSPLASH:-0}" = "1" ]; then
    echo "==> Splash screen disabled (NOSPLASH=1)"
elif [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    python3 /app/lib/boosteroid/splash.py &
    SPLASH_PID=$!
fi

XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
INSTALL_DIR="${XDG_DATA_HOME}/boosteroid"
BINARY="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./bin/Boosteroid"
LIB_DIR="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./lib"

# ── First-run install ────────────────────────────────────────────────────────
if [ ! -f "${BINARY}" ]; then
    echo "==> First launch: downloading Boosteroid..."
    python3 /app/lib/boosteroid/install_boosteroid.py
fi

# Always ensure the Steam shortcut exists (idempotent — skips if already present).
# Runs on every launch so reinstalling the flatpak re-adds the shortcut if needed.
echo "==> Ensuring Steam shortcut..."
python3 /app/lib/boosteroid/add-to-steam.py \
    || echo "Warning: could not add Steam shortcut (is Steam installed?)"

# ── AMD GPU optimisation ─────────────────────────────────────────────────────
# Detect AMD GPU via PCI vendor ID (0x1002 = AMD/ATI).
# Sets the radeonsi VA-API driver and passes -vaapi to Boosteroid so hardware
# video decode is used for the stream instead of software decode.
DECODE_FLAG=""
if grep -q "0x1002" /sys/class/drm/renderD128/device/vendor 2>/dev/null; then
    export LIBVA_DRIVER_NAME="${LIBVA_DRIVER_NAME:-radeonsi}"
    DECODE_FLAG="-vaapi"
fi

# ── Google login (xdg-open via host) ────────────────────────────────────────
# In Game Mode (Gamescope) there is no traditional desktop environment, so the
# Flatpak portal and host xdg-open may not work reliably.  The most reliable
# approach is to use Steam's built-in browser via the steam://openurl/ protocol.
# Steam is always running in Game Mode and its overlay browser can follow the
# loopback OAuth redirect (http://localhost:PORT/callback) because the Flatpak
# sandbox shares the host network namespace (--share=network).
# Fallback: host xdg-open works in Desktop Mode where a normal browser is running.
_OVERRIDE_BIN="${XDG_RUNTIME_DIR}/boosteroid-bin"
mkdir -p "${_OVERRIDE_BIN}"
cat > "${_OVERRIDE_BIN}/xdg-open" << 'EOF'
#!/bin/bash
URL="$1"
echo "[xdg-open] called with: $URL" >> $HOME/logs/boosteroid.log

# Method 1: Steam overlay browser — works in Game Mode and Desktop Mode on SteamOS.
# Tells the already-running Steam process to open the URL in its built-in browser.
if flatpak-spawn --host steam "steam://openurl/$URL" >> $HOME/logs/boosteroid.log 2>&1; then
    echo "[xdg-open] steam://openurl OK" >> $HOME/logs/boosteroid.log
    exit 0
fi
echo "[xdg-open] steam://openurl failed, trying host xdg-open" >> $HOME/logs/boosteroid.log

# Method 2: host xdg-open — fallback for Desktop Mode if Steam isn't in PATH.
flatpak-spawn --host xdg-open "$URL" >> $HOME/logs/boosteroid.log 2>&1
echo "[xdg-open] xdg-open exit=$?" >> $HOME/logs/boosteroid.log
EOF
chmod +x "${_OVERRIDE_BIN}/xdg-open"
export PATH="${_OVERRIDE_BIN}:${PATH}"

# ── Wait for any previous Boosteroid instance to exit ────────────────────────
# Detection strategy:
#   1. STATUS_FILE contains the numeric PID written by the previous launcher.
#      Check /proc/$pid/comm for "boosteroid" — instant and reliable even if
#      the previous launcher was killed before cleanup (SIGKILL).
#   2. Non-PID / absent STATUS_FILE = stale file from old version or crashed
#      session.  Kill any orphaned pgrep matches immediately and proceed —
#      do NOT enter the retry loop.  This avoids the warn: state that caused
#      the splash to close before Boosteroid launched.
_wait_for_boosteroid_close() {
    local _pid="" _should_wait=0

    if [ -f "${STATUS_FILE}" ]; then
        local _content
        _content=$(cat "${STATUS_FILE}" 2>/dev/null || true)
        if [[ "${_content}" =~ ^[0-9]+$ ]]; then
            _pid="${_content}"
            if [ -d "/proc/${_pid}" ] && grep -qi "boosteroid" "/proc/${_pid}/comm" 2>/dev/null; then
                echo "==> STATUS_FILE: PID ${_pid} still running (Boosteroid confirmed)"
                _should_wait=1
            else
                echo "==> STATUS_FILE: PID ${_pid} is gone, clearing"
                rm -f "${STATUS_FILE}"
            fi
        else
            # Non-PID content = stale file from old version or crashed session.
            # Kill any lingering processes and proceed — never retry stale state.
            echo "==> STATUS_FILE has stale content (${_content:0:20}...), killing orphaned processes"
            rm -f "${STATUS_FILE}"
            flatpak-spawn --host pkill -f "BoosteroidGamesS" 2>/dev/null || true
            sleep 0.5
        fi
    else
        # No STATUS_FILE.  Kill any orphaned processes left by a previous crash.
        if flatpak-spawn --host pgrep -f "BoosteroidGamesS" > /dev/null 2>&1; then
            echo "==> No STATUS_FILE but orphaned Boosteroid found, killing"
            flatpak-spawn --host pkill -f "BoosteroidGamesS" 2>/dev/null || true
            sleep 0.5
        fi
    fi

    [ "${_should_wait}" -eq 1 ] || return 0

    # Wait for the PID-tracked instance to exit gracefully.
    echo "==> Previous Boosteroid (PID ${_pid}) still running, waiting..."
    local max_attempts=5 wait_secs=3 i=1
    while [ "$i" -le "$max_attempts" ]; do
        echo "step:Waiting for previous Boosteroid to close (${i}/${max_attempts})..." \
            > "${STATUS_FILE}"
        echo "==> Attempt ${i}/${max_attempts}: still running, retrying in ${wait_secs}s..."
        sleep "${wait_secs}" || {
            echo "==> Wait sleep interrupted — proceeding with launch"
            rm -f "${STATUS_FILE}"
            return 0
        }
        if ! { [ -d "/proc/${_pid}" ] && grep -qi "boosteroid" "/proc/${_pid}/comm" 2>/dev/null; }; then
            rm -f "${STATUS_FILE}"
            echo "==> Previous instance exited OK"
            return 0
        fi
        i=$((i + 1))
    done

    # Still running after waiting — force-kill and proceed.
    echo "==> Force-killing previous Boosteroid (PID ${_pid}) after ${max_attempts} attempts"
    flatpak-spawn --host kill -9 "${_pid}" 2>/dev/null || true
    sleep 0.5
    rm -f "${STATUS_FILE}"
}
_wait_for_boosteroid_close

# ── Portal intercept for Google login ───────────────────────────────────────
# Qt5 calls org.freedesktop.portal.Desktop.OpenURI via D-Bus instead of
# xdg-open, bypassing our PATH wrapper.  We claim that portal name on the
# sandbox proxy bus and redirect all OpenURI calls to steam://openurl/ so
# the Steam overlay browser handles Google OAuth in both Game Mode and Desktop.
python3 /app/lib/boosteroid/portal_openuri.py &
sleep 0.3   # let the service register before Boosteroid starts

# ── Force fullscreen ─────────────────────────────────────────────────────────
# Runs in the background: polls for the Boosteroid X11 window and sends it a
# _NET_WM_STATE_FULLSCREEN ClientMessage so it fills the Gamescope display
# without any user interaction.
/app/bin/boosteroid-fullscreen >> "$LOG" 2>&1 &

# ── Launch ───────────────────────────────────────────────────────────────────
# Add Boosteroid's bundled libraries to the search path.
export LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# Wait for the splash to finish before starting Boosteroid.
# Boosteroid immediately maps a fullscreen window and Gamescope switches
# focus to it, hiding the splash — so we must launch only after splash exits.
if [ -n "${SPLASH_PID}" ]; then
    wait "${SPLASH_PID}" 2>/dev/null || true
fi

# ── Session stats ────────────────────────────────────────────────────────────
# Steam kills games with SIGKILL in Game Mode, so exit handlers never run.
# Strategy: write start timestamp, then on NEXT launch close any unclosed session
# by calculating duration from the start timestamp.
STATS_FILE="$HOME/logs/boosteroid-stats.csv"
if [ ! -f "$STATS_FILE" ]; then
    echo "timestamp,event,version,duration_s,decoder" > "$STATS_FILE"
fi

# Close any previous unclosed session (last line is a "start" with no matching "end").
_close_previous_session() {
    local last_line last_event start_ts start_epoch end_epoch dur
    last_line=$(tail -1 "$STATS_FILE")
    last_event=$(echo "$last_line" | cut -d',' -f2)
    if [ "$last_event" = "start" ]; then
        start_ts=$(echo "$last_line" | cut -d',' -f1)
        start_epoch=$(date -d "$start_ts" +%s 2>/dev/null) || return
        # Use boosteroid.log mtime as the best estimate of when the session ended.
        if [ -f "$LOG" ]; then
            end_epoch=$(stat -c %Y "$LOG" 2>/dev/null) || end_epoch=$(date +%s)
        else
            end_epoch=$(date +%s)
        fi
        dur=$((end_epoch - start_epoch))
        if [ "$dur" -lt 0 ] || [ "$dur" -gt 86400 ]; then
            dur=0
        fi
        echo "$(date -d "@${end_epoch}" -Iseconds 2>/dev/null || date -Iseconds),end,${VERSION},${dur},$(echo "$last_line" | cut -d',' -f5)" >> "$STATS_FILE"
        echo "==> Closed previous session (${dur}s, from log mtime)"
    fi
}
_close_previous_session

# ── Filter debug output unless DEBUG=1 ──────────────────────────────────────
# By default [debug] lines from Boosteroid are stripped from the log.
# To keep them, add --env=DEBUG=1 to Steam launch options:
#   run --env=DEBUG=1 org.schelstraete.boosteroid
#
# Run Boosteroid in the background so we can capture its PID and write it to
# STATUS_FILE.  The next launcher reads that PID and checks /proc/$pid/comm —
# no age heuristic, works correctly even if this launcher is SIGKILL'd.
# shellcheck disable=SC2086
if [ "${DEBUG:-0}" = "1" ]; then
    echo "==> Debug mode ON: [debug] lines will appear in log"
    "${BINARY}" ${DECODE_FLAG} "$@" &
else
    # Process substitution keeps $! as Boosteroid's PID (not grep's).
    "${BINARY}" ${DECODE_FLAG} "$@" > >(grep --line-buffered -v '\[debug\]') 2>&1 &
fi
BOOSTEROID_PID=$!
echo "${BOOSTEROID_PID}" > "${STATUS_FILE}"
echo "==> Boosteroid started (PID ${BOOSTEROID_PID})"
echo "$(date -Iseconds),start,${VERSION},0,${DECODE_FLAG:--none-}" >> "$STATS_FILE"

wait "${BOOSTEROID_PID}" || true

# Write session end if we reach here (clean exit — rare in Game Mode).
SESSION_END=$(date +%s)
SESSION_START_TS=$(tail -1 "$STATS_FILE" | cut -d',' -f1)
SESSION_START_EPOCH=$(date -d "$SESSION_START_TS" +%s 2>/dev/null || echo "$SESSION_END")
SESSION_DUR=$((SESSION_END - SESSION_START_EPOCH))
echo "$(date -Iseconds),end,${VERSION},${SESSION_DUR},${DECODE_FLAG:--none-}" >> "$STATS_FILE"
echo "==> Session duration: ${SESSION_DUR}s"

# Remove the running indicator now that Boosteroid has exited.
rm -f "${STATUS_FILE}"
echo "==> Boosteroid exited"
