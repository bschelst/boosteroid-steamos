#!/usr/bin/env python3
"""
Fake org.freedesktop.portal.OpenURI service using gi.repository.Gio.

Author: Schelstraete Bart
        https://github.com/bschelst/boosteroid-steamos
        https://www.schelstraete.org

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
import threading

import os
LOG = os.path.join(os.path.expanduser("~"), "logs", "boosteroid.log")


def log(s):
    try:
        with open(LOG, "a") as f:
            f.write(f"[portal] {s}\n")
    except OSError:
        pass


try:
    import gi
    gi.require_version("GLib", "2.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gio, Gtk
except ImportError as e:
    log(f"gi unavailable ({e}) — portal intercept disabled")
    sys.exit(0)


def _show_index_hint():
    """Show a GTK dialog from within the Flatpak (display always accessible here)."""
    try:
        dlg = Gtk.Dialog(title="Install Index")
        dlg.set_default_size(420, -1)

        content = dlg.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(16)
        content.set_margin_bottom(8)
        content.set_margin_start(16)
        content.set_margin_end(16)

        label = Gtk.Label()
        label.set_markup(
            "Install <b>Index</b> from Flathub to browse and play\n"
            "your recorded clips in Game Mode."
        )
        label.set_line_wrap(True)
        content.add(label)

        dlg.add_button("Later", Gtk.ResponseType.CANCEL)
        install_btn = dlg.add_button("Install", Gtk.ResponseType.OK)
        dlg.show_all()

        installing = [False]  # mutable flag — prevents re-trigger on Close click

        def on_response(d, response_id):
            if response_id != Gtk.ResponseType.OK or installing[0]:
                d.destroy()
                return
            installing[0] = True
            label.set_text("Installing… please wait.")
            install_btn.set_sensitive(False)

            def do_install():
                r = subprocess.run(
                    ["flatpak-spawn", "--host", "flatpak", "install",
                     "--user", "--noninteractive", "flathub", "org.kde.index"],
                    capture_output=True,
                )

                def on_done():
                    if r.returncode == 0:
                        label.set_text(
                            "Index installed!\n"
                            "Close and tap 'Open Clip Location' again."
                        )
                    else:
                        err = r.stderr.decode(errors="replace").strip()[-120:]
                        label.set_text(f"Install failed:\n{err}")
                    install_btn.set_label("Close")
                    install_btn.set_sensitive(True)
                    return False

                GLib.idle_add(on_done)

            threading.Thread(target=do_install, daemon=True).start()

        dlg.connect("response", on_response)
    except Exception as exc:
        log(f"hint dialog error: {exc}")
    return False


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


def on_method_call(conn, sender, path, iface, method, params, invoc, *_args):
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
        try:
            msg = invoc.get_message()
            fd_list = msg.get_unix_fd_list()
            fd = fd_list.get(params[1])
            path = os.readlink(f"/proc/self/fd/{fd}")
            os.close(fd)
            log(f"OpenFile: {path}")
            if os.environ.get("GAMESCOPE_WAYLAND_DISPLAY"):
                # Game Mode: prefer org.kde.index (touch-friendly Flatpak).
                # If not installed, show a hint via kdialog/zenity.
                r = subprocess.run(
                    ["flatpak-spawn", "--host", "flatpak", "info", "org.kde.index"],
                    capture_output=True,
                )
                if r.returncode == 0:
                    log("OpenFile: Game Mode — launching org.kde.index")
                    subprocess.Popen(["flatpak-spawn", "--host", "flatpak", "run", "org.kde.index", path])
                else:
                    log("OpenFile: Game Mode — org.kde.index not installed, showing GTK hint")
                    GLib.idle_add(_show_index_hint)
            else:
                # Desktop Mode: use the system file manager directly.
                log("OpenFile: Desktop Mode — opening with dolphin/nautilus")
                subprocess.Popen([
                    "flatpak-spawn", "--host", "bash", "-c",
                    'dolphin "$1" 2>/dev/null || nautilus "$1" 2>/dev/null || xdg-open "$1"',
                    "--", path,
                ])
        except Exception as exc:
            log(f"OpenFile error: {exc}")
        invoc.return_value(GLib.Variant("(o)", (REQUEST_PATH,)))
    else:
        invoc.return_dbus_error(
            "org.freedesktop.DBus.Error.UnknownMethod", f"Unknown: {method}"
        )


def on_bus_acquired(conn, name, *_args):
    node_info = Gio.DBusNodeInfo.new_for_xml(PORTAL_XML)
    conn.register_object(
        "/org/freedesktop/portal/desktop",
        node_info.interfaces[0],
        on_method_call,
        None,
        None,
    )
    log("portal service registered on bus")


def on_name_acquired(_conn, name, *_args):
    log(f"portal name acquired: {name} — Google login intercept active")


def on_name_lost(_conn, name, *_args):
    # This fires when: (a) the name was never acquired (already taken) or
    # (b) we lost it after acquiring it.  Log but keep the GLib loop alive
    # so the registered D-Bus object stays reachable if we ever do own it.
    log(f"portal name lost/denied: {name} — will retry with REPLACE")


log("portal service starting (gi.repository.Gio)...")
# REPLACE: take the name from whoever holds it on the Flatpak proxy bus.
# The --own-name=org.freedesktop.portal.Desktop manifest permission allows this.
Gio.bus_own_name(
    Gio.BusType.SESSION,
    "org.freedesktop.portal.Desktop",
    Gio.BusNameOwnerFlags.REPLACE,
    on_bus_acquired,
    on_name_acquired,
    on_name_lost,
)
GLib.MainLoop().run()
