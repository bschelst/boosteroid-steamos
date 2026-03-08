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
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GLib, Gio, Gtk, GdkPixbuf
except ImportError as e:
    log(f"gi unavailable ({e}) — portal intercept disabled")
    sys.exit(0)


def _play_file(filepath):
    """Play a video using GStreamer within the Flatpak (display always accessible)."""
    log(f"play: {filepath}")
    try:
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)

        player = Gst.ElementFactory.make("playbin", "player")
        if player is None:
            log("play: GStreamer playbin unavailable")
            return

        player.set_property("uri", GLib.filename_to_uri(filepath, None))
        player.set_state(Gst.State.PLAYING)

        bus = player.get_bus()
        bus.add_signal_watch()

        def on_message(_bus, msg):
            if msg.type == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                log(f"play error: {err} — {dbg}")
                player.set_state(Gst.State.NULL)
            elif msg.type == Gst.MessageType.EOS:
                log("play: done")
                player.set_state(Gst.State.NULL)

        bus.connect("message", on_message)
    except Exception as exc:
        log(f"play exception: {exc}")


def _open_clips_browser(path):
    """GTK file chooser opened from within the Flatpak — works in Game Mode."""
    try:
        dialog = Gtk.FileChooserDialog(title="Boosteroid SteamOS Clips")
        dialog.set_action(Gtk.FileChooserAction.OPEN)
        dialog.set_current_folder(path)
        dialog.set_default_size(900, 600)

        # Gamescope doesn't add window decorations — provide our own header bar
        # with a close button so the user can dismiss the dialog.
        header = Gtk.HeaderBar()
        header.set_title("Boosteroid SteamOS Clips")
        header.set_show_close_button(True)
        dialog.set_titlebar(header)

        filt = Gtk.FileFilter()
        filt.set_name("Video files")
        filt.add_mime_type("video/*")
        dialog.add_filter(filt)

        dialog.add_button("Close", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)
        dialog.show_all()

        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.OK:
                filepath = d.get_filename()
                if filepath:
                    _play_file(filepath)
                return  # keep dialog open so user can open more files
            d.destroy()

        dialog.connect("response", on_response)
    except Exception as exc:
        log(f"clips browser error: {exc}")
    return False


_CSS = b"""
window {
    background-color: #1b1b2e;
}
box {
    background-color: transparent;
}
label.title {
    color: #ffffff;
    font-size: 18px;
    font-weight: bold;
}
label.desc {
    color: #cccccc;
    font-size: 14px;
}
button.install {
    background-image: none;
    background-color: #1a9fff;
    color: #ffffff;
    border-radius: 6px;
    border: none;
    padding: 8px 24px;
    font-size: 14px;
    font-weight: bold;
    min-width: 120px;
}
button.install:hover {
    background-color: #2aafff;
}
button.install:disabled {
    background-color: #334455;
    color: #667788;
}
button.later {
    background-image: none;
    background-color: transparent;
    color: #888888;
    border: 1px solid #334455;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    min-width: 100px;
}
button.later:hover {
    background-color: #223344;
}
"""


def _show_index_hint():
    """Show a modern branded GTK window from within the Flatpak."""
    try:
        win = Gtk.Window()
        win.set_title("Install Index")
        win.set_default_size(480, -1)
        win.set_resizable(False)
        win.set_position(Gtk.WindowPosition.CENTER)

        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            win.get_screen(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_margin_top(32)
        outer.set_margin_bottom(32)
        outer.set_margin_start(32)
        outer.set_margin_end(32)
        win.add(outer)

        # Logo
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                "/app/share/boosteroid/icon-256.png", 96, 96,
            )
            img = Gtk.Image.new_from_pixbuf(pixbuf)
        except Exception:
            img = Gtk.Image.new_from_icon_name("package-x-generic", Gtk.IconSize.DIALOG)
        img.set_margin_bottom(16)
        outer.pack_start(img, False, False, 0)

        # Title
        title = Gtk.Label(label="Browse clips in Game Mode")
        title.get_style_context().add_class("title")
        title.set_margin_bottom(8)
        outer.pack_start(title, False, False, 0)

        # Description / status
        label = Gtk.Label(label="Install Index from Flathub to browse\nand play your recorded clips.")
        label.get_style_context().add_class("desc")
        label.set_justify(Gtk.Justification.CENTER)
        label.set_margin_bottom(32)
        outer.pack_start(label, False, False, 0)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        outer.pack_start(btn_box, False, False, 0)

        later_btn = Gtk.Button(label="Later")
        later_btn.get_style_context().add_class("later")
        btn_box.pack_start(later_btn, False, False, 0)

        install_btn = Gtk.Button(label="Install")
        install_btn.get_style_context().add_class("install")
        btn_box.pack_start(install_btn, False, False, 0)

        win.show_all()

        installing = [False]

        def on_later(*_):
            win.destroy()

        def on_install(*_):
            if installing[0]:
                win.destroy()
                return
            installing[0] = True
            label.set_text("Installing... please wait.")
            install_btn.set_sensitive(False)
            later_btn.set_sensitive(False)

            def do_install():
                r = subprocess.run(
                    ["flatpak-spawn", "--host", "flatpak", "install",
                     "--user", "--noninteractive", "flathub", "org.kde.index"],
                    capture_output=True,
                )

                def on_done():
                    if r.returncode == 0:
                        label.set_text("Installed! Close and tap\n'Open Clip Location' again.")
                    else:
                        err = r.stderr.decode(errors="replace").strip()[-100:]
                        label.set_text(f"Install failed:\n{err}")
                    install_btn.set_label("Close")
                    install_btn.set_sensitive(True)
                    return False

                GLib.idle_add(on_done)

            threading.Thread(target=do_install, daemon=True).start()

        later_btn.connect("clicked", on_later)
        install_btn.connect("clicked", on_install)

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
                # Game Mode: external apps can't connect to Gamescope's Wayland
                # socket when spawned via flatpak-spawn --host (Connection refused).
                # Show a GTK file chooser from within our own Flatpak instead —
                # we already have display access since we're running inside Gamescope.
                log("OpenFile: Game Mode — showing GTK file browser")
                GLib.idle_add(lambda: _open_clips_browser(path))
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
