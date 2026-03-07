#!/usr/bin/env python3
"""
Fake org.freedesktop.portal.OpenURI service.

Qt5 inside a Flatpak calls org.freedesktop.portal.Desktop.OpenURI via D-Bus
instead of xdg-open, bypassing any PATH-based wrapper.  By claiming
org.freedesktop.portal.Desktop on the sandbox proxy bus before Boosteroid
starts, we intercept every OpenURI call and redirect it to Steam's built-in
browser via steam://openurl/ — the only browser guaranteed to be visible in
Game Mode (Gamescope).

Requires --own-name=org.freedesktop.portal.Desktop in the Flatpak manifest.
"""
import os
import subprocess
import sys

LOG = "/tmp/boosteroid.log"


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"[portal] {msg}\n")
    except OSError:
        pass


try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
except ImportError as e:
    log(f"dbus/gi unavailable ({e}) — portal intercept disabled, xdg-open fallback in effect")
    sys.exit(0)

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.OpenURI"
REQUEST_PATH = dbus.ObjectPath(PORTAL_PATH + "/request/boosteroid/1")


class FakePortal(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, dbus.ObjectPath(PORTAL_PATH))

    @dbus.service.method(PORTAL_IFACE, in_signature="ssa{sv}", out_signature="o")
    def OpenURI(self, parent_window, uri, options):
        log(f"OpenURI: {uri}")
        try:
            r = subprocess.run(
                ["flatpak-spawn", "--host", "steam", f"steam://openurl/{uri}"],
                capture_output=True, timeout=5,
            )
            log(f"steam://openurl exit={r.returncode}")
            if r.returncode != 0:
                subprocess.Popen(["flatpak-spawn", "--host", "xdg-open", uri])
                log("fell back to host xdg-open")
        except Exception as exc:
            log(f"error: {exc}")
        return REQUEST_PATH

    @dbus.service.method(PORTAL_IFACE, in_signature="sha{sv}", out_signature="o")
    def OpenFile(self, parent_window, fd, options):
        log("OpenFile (ignored)")
        return REQUEST_PATH


dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()

try:
    bus_name = dbus.service.BusName(PORTAL_NAME, bus,
                                    allow_replacement=False,
                                    replace_existing=False,
                                    do_not_queue=True)
except dbus.exceptions.NameExistsException:
    log(f"{PORTAL_NAME} already owned — portal intercept disabled")
    sys.exit(0)
except Exception as e:
    log(f"could not claim {PORTAL_NAME}: {e} — portal intercept disabled")
    sys.exit(0)

FakePortal(bus)
log("portal intercept active")
GLib.MainLoop().run()
