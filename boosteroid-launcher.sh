#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.

set -euo pipefail

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

# ── Google login in Game Mode ────────────────────────────────────────────────
# Gamescope (Steam Deck Game Mode) has no standalone browser, but Steam itself
# is registered as the HTTP handler in the Gamescope session.
# We inject an xdg-open wrapper that calls flatpak-spawn --host so OAuth URLs
# are forwarded to the HOST's xdg-open → Steam's built-in browser opens.
if [ -n "${GAMESCOPE_WAYLAND_DISPLAY:-}" ]; then
    _OVERRIDE_BIN="${XDG_RUNTIME_DIR}/boosteroid-bin"
    mkdir -p "${_OVERRIDE_BIN}"
    cat > "${_OVERRIDE_BIN}/xdg-open" << 'EOF'
#!/bin/bash
flatpak-spawn --host xdg-open "$@" 2>/dev/null || true
EOF
    chmod +x "${_OVERRIDE_BIN}/xdg-open"
    export PATH="${_OVERRIDE_BIN}:${PATH}"
fi

# ── Launch ───────────────────────────────────────────────────────────────────
# Add Boosteroid's bundled libraries to the search path.
export LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

# shellcheck disable=SC2086
exec "${BINARY}" ${DECODE_FLAG} "$@"
