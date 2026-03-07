#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.

set -euo pipefail

# ── Debug log (check /tmp/boosteroid.log from Desktop Mode after launch) ─────
LOG=/tmp/boosteroid.log
exec > >(tee -a "$LOG") 2>&1
VERSION=$(cat /app/share/boosteroid/version 2>/dev/null || echo "unknown")
echo "=== Boosteroid $VERSION launch $(date) ==="
echo "DISPLAY=${DISPLAY:-<unset>}  WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-<unset>}"
echo "GAMESCOPE_WAYLAND_DISPLAY=${GAMESCOPE_WAYLAND_DISPLAY:-<unset>}"
echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-<unset>}"

XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
INSTALL_DIR="${XDG_DATA_HOME}/boosteroid"
BINARY="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./bin/Boosteroid"
LIB_DIR="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./lib"

# ── First-run install ────────────────────────────────────────────────────────
if [ ! -f "${BINARY}" ]; then
    echo "==> First launch: downloading Boosteroid..."
    python3 /app/lib/boosteroid/install_boosteroid.py

    echo "==> Adding Boosteroid to your Steam library..."
    python3 /app/lib/boosteroid/add-to-steam.py \
        || echo "Warning: could not add Steam shortcut (is Steam installed?)"
fi

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
# In Desktop Mode the Flatpak portal handles xdg-open fine.
# In Game Mode, GAMESCOPE_WAYLAND_DISPLAY is often not forwarded into the
# sandbox, so a conditional guard is unreliable. We always inject a wrapper
# that uses flatpak-spawn --host so OAuth URLs escape the sandbox and reach
# the host's xdg-open — which in SteamOS routes http/https to Steam's
# built-in browser in both modes.
_OVERRIDE_BIN="${XDG_RUNTIME_DIR}/boosteroid-bin"
mkdir -p "${_OVERRIDE_BIN}"
cat > "${_OVERRIDE_BIN}/xdg-open" << 'EOF'
#!/bin/bash
echo "[xdg-open] called with: $*" >> /tmp/boosteroid.log
flatpak-spawn --host xdg-open "$@"
echo "[xdg-open] flatpak-spawn exit=$?" >> /tmp/boosteroid.log
EOF
chmod +x "${_OVERRIDE_BIN}/xdg-open"
export PATH="${_OVERRIDE_BIN}:${PATH}"

# ── Force fullscreen ─────────────────────────────────────────────────────────
# Runs in the background: polls for the Boosteroid X11 window and sends it a
# _NET_WM_STATE_FULLSCREEN ClientMessage so it fills the Gamescope display
# without any user interaction.
/app/bin/boosteroid-fullscreen >> "$LOG" 2>&1 &

# ── Launch ───────────────────────────────────────────────────────────────────
# Add Boosteroid's bundled libraries to the search path.
export LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# shellcheck disable=SC2086
exec "${BINARY}" ${DECODE_FLAG} "$@"
