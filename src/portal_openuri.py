#!/usr/bin/env python3
"""
Fake org.freedesktop.portal.OpenURI service using gi.repository.Gio.

Qt5 inside a Flatpak calls org.freedesktop.portal.Desktop.OpenURI via D-Bus
instead of xdg-open, bypassing any PATH-based wrapper.  By claiming
org.freedesktop.portal.Desktop on the sandbox proxy bus before Boosteroid
starts, we intercept every OpenURI call and redirect it to Steam's built-in
browser via steam://openurl/.

Uses gi.repository.Gio (GObject introspection) — always present in the
freedesktop 24.08 runtime — instead of dbus-python which is not.
Requires --own-name=org.freedesktop.portal.Desktop in the Flatpak manifest.
"""
import subprocess
import sys

LOG = "/tmp/boosteroid.log"


def log(s):
    try:
        with open(LOG, "a") as f:
            f.write(f"[portal] {s}\n")
    except OSError:
        pass


try:
    import gi
    gi.require_version("GLib", "2.0")
    from gi.repository import GLib, Gio
except ImportError as e:
    log(f"gi unavailable ({e}) — portal intercept disabled")
    sys.exit(0)


PORTAL_XML = """
<node>
  <interface name='org.freedesktop.portal.OpenURI'>
    <method name='OpenURI'>
      <arg type='s' name='parent_window' direction='in'/>
      <arg type='s' name='uri' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
    <method name='OpenFile'>
      <arg type='s' name='parent_window' direction='in'/>
      <arg type='h' name='fd' direction='in'/>
      <arg type='a{sv}' name='options' direction='in'/>
      <arg type='o' name='handle' direction='out'/>
    </method>
  </interface>
</node>"""

REQUEST_PATH = "/org/freedesktop/portal/desktop/request/boosteroid/1"


def on_method_call(conn, sender, path, iface, method, params, invoc, _user_data):
    if method == "OpenURI":
        uri = params[1]
        log(f"OpenURI: {uri}")
        try:
            r = subprocess.run(
                ["flatpak-spawn", "--host", "steam", f"steam://openurl/{uri}"],
                capture_output=True, timeout=5,
            )
            log(f"steam exit={r.returncode}")
            if r.returncode != 0:
                subprocess.Popen(["flatpak-spawn", "--host", "xdg-open", uri])
                log("fell back to xdg-open")
        except Exception as exc:
            log(f"error: {exc}")
        invoc.return_value(GLib.Variant("(o)", (REQUEST_PATH,)))
    elif method == "OpenFile":
        log("OpenFile (ignored)")
        invoc.return_value(GLib.Variant("(o)", (REQUEST_PATH,)))
    else:
        invoc.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod", f"Unknown: {method}"
        )


def on_bus_acquired(conn, name, _user_data):
    node_info = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
    conn.register_object(
        "/org/freedesktop/portal/desktop",
        node_info.interfaces[0],
        on_method_call,
        None,
        None,
    )
    log("portal service registered on bus")


def on_name_acquired(_conn, name, _user_data):
    log(f"portal name acquired: {name} — Google login intercept active")


def on_name_lost(_conn, name, _user_data):
    log(f"portal name lost/denied: {name} — intercept disabled")
    sys.exit(0)


log("portal service starting (gi.repository.Gio)...")
Gio.bus_own_name(
    Gio.BusType.SESSION,
    "org.freedesktop.portal.Desktop",
    Gio.BusNameOwnerFlags.NONE,
    on_bus_acquired,
    on_name_acquired,
    on_name_lost,
)
GLib.MainLoop().run()
