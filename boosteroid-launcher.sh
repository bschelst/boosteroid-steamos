#!/bin/bash
# Launcher for the Boosteroid Flatpak.
# On first run: downloads Boosteroid from boosteroid.com and adds a Steam shortcut.
# Subsequent runs: launches the cached binary directly.

set -euo pipefail

XDG_DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
INSTALL_DIR="${XDG_DATA_HOME}/boosteroid"
BINARY="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./bin/Boosteroid"
LIB_DIR="${INSTALL_DIR}/opt/BoosteroidGamesS.R.L./lib"

if [ ! -f "${BINARY}" ]; then
    echo "==> First launch: downloading Boosteroid..."
    python3 /app/lib/boosteroid/install_boosteroid.py

    echo "==> Adding Boosteroid to your Steam library..."
    python3 /app/lib/boosteroid/add-to-steam.py \
        || echo "Warning: could not add Steam shortcut (is Steam installed?)"
fi

# Add Boosteroid's bundled libraries to the search path
export LD_LIBRARY_PATH="${LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

exec "${BINARY}" "$@"
