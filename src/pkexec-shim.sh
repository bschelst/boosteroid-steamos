#!/bin/bash
# pkexec shim for Flatpak — runs commands without privilege escalation.
# Handles "Text file busy" when the updater tries to overwrite the running binary:
# unlink the target first (Linux keeps the old inode alive), then retry the copy.
LOG="$HOME/logs/boosteroid.log"
echo "[pkexec shim] $*" >> "$LOG"

if "$@" 2>>"$LOG"; then
    exit 0
fi

# cp -a failed — likely "Text file busy".  Find the destination directory
# (last argument) and remove busy files before retrying.
ARGS=("$@")
DEST="${ARGS[${#ARGS[@]}-1]}"
if [ -d "$DEST" ]; then
    echo "[pkexec shim] retrying: removing busy files in $DEST" >> "$LOG"
    find "$DEST" -maxdepth 1 -type f -exec rm -f {} +
    exec "$@"
fi

exit 1
