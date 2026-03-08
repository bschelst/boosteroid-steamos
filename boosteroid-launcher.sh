#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.

set -euo pipefail

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

# Dismiss the splash screen now that Boosteroid is ready to start.
if [ -n "${SPLASH_PID}" ] && kill -0 "${SPLASH_PID}" 2>/dev/null; then
    kill "${SPLASH_PID}" 2>/dev/null || true
    wait "${SPLASH_PID}" 2>/dev/null || true
fi

# shellcheck disable=SC2086
exec "${BINARY}" ${DECODE_FLAG} "$@"
