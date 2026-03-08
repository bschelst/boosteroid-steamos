#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.

set -euo pipefail

# Shared with splash screen for live status updates
STATUS_FILE="/tmp/.boosteroid_splash_status"

# ── Debug log (check /tmp/boosteroid.log from Desktop Mode after launch) ─────
LOG=/tmp/boosteroid.log
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
SPLASH_PID=""
if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
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
echo "[xdg-open] called with: $URL" >> /tmp/boosteroid.log

# Method 1: Steam overlay browser — works in Game Mode and Desktop Mode on SteamOS.
# Tells the already-running Steam process to open the URL in its built-in browser.
if flatpak-spawn --host steam "steam://openurl/$URL" >> /tmp/boosteroid.log 2>&1; then
    echo "[xdg-open] steam://openurl OK" >> /tmp/boosteroid.log
    exit 0
fi
echo "[xdg-open] steam://openurl failed, trying host xdg-open" >> /tmp/boosteroid.log

# Method 2: host xdg-open — fallback for Desktop Mode if Steam isn't in PATH.
flatpak-spawn --host xdg-open "$URL" >> /tmp/boosteroid.log 2>&1
echo "[xdg-open] xdg-open exit=$?" >> /tmp/boosteroid.log
EOF
chmod +x "${_OVERRIDE_BIN}/xdg-open"
export PATH="${_OVERRIDE_BIN}:${PATH}"

# ── Wait for any previous Boosteroid instance to exit ────────────────────────
# Boosteroid can take a few seconds to fully shut down after the user quits.
# Re-launching before it exits can cause the new session to fail.
# We poll the host process list (via flatpak-spawn) and update the splash.
_wait_for_boosteroid_close() {
    local max_attempts=5 wait_secs=4 i=1
    if ! flatpak-spawn --host pgrep -f "BoosteroidGamesS" > /dev/null 2>&1; then
        return 0
    fi
    echo "==> Previous Boosteroid instance still running, waiting..."
    while flatpak-spawn --host pgrep -f "BoosteroidGamesS" > /dev/null 2>&1; do
        if [ "$i" -gt "$max_attempts" ]; then
            echo "warn:Previous Boosteroid still running after ${max_attempts} retries — launching anyway" \
                > "${STATUS_FILE}"
            echo "==> Warning: still running after ${max_attempts} attempts, launching anyway"
            return 0
        fi
        echo "step:Waiting for previous Boosteroid to close (${i}/${max_attempts})..." \
            > "${STATUS_FILE}"
        echo "==> Attempt ${i}/${max_attempts}: still running, retrying in ${wait_secs}s..."
        sleep "${wait_secs}"
        i=$((i + 1))
    done
    rm -f "${STATUS_FILE}"
    echo "==> Previous instance exited OK"
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

# Ensure status file is gone before launch so splash closes normally
rm -f "${STATUS_FILE}"

# Wait for the splash to finish before starting Boosteroid.
# Boosteroid immediately maps a fullscreen window and Gamescope switches
# focus to it, hiding the splash — so we must exec only after splash exits.
if [ -n "${SPLASH_PID}" ]; then
    wait "${SPLASH_PID}" 2>/dev/null || true
fi

# ── Filter debug output unless DEBUG=1 ──────────────────────────────────────
# By default [debug] lines from Boosteroid are stripped from the log.
# To keep them, add --env=DEBUG=1 to Steam launch options:
#   run --env=DEBUG=1 org.schelstraete.boosteroid
# shellcheck disable=SC2086
if [ "${DEBUG:-0}" = "1" ]; then
    echo "==> Debug mode ON: [debug] lines will appear in log"
    exec "${BINARY}" ${DECODE_FLAG} "$@"
else
    "${BINARY}" ${DECODE_FLAG} "$@" 2>&1 | grep --line-buffered -v '\[debug\]'
fi
