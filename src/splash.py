#!/usr/bin/env python3
"""
Splash screen for Boosteroid SteamOS (unofficial).
"""

import sys
import os
import socket
import threading

os.environ.setdefault("GDK_BACKEND", "x11")

def _log(msg):
    print(f"[splash] {msg}", file=sys.stderr, flush=True)

_log("starting")

try:
    _log("importing gi")
    import gi
    _log("gi imported")
    gi.require_version('Gtk', '3.0')
    _log("requiring Gtk 3.0")
    from gi.repository import Gtk, GLib, Gdk
    _log("Gtk imported")
except Exception as e:
    _log(f"GTK unavailable, skipping: {e}")
    sys.exit(0)

MAX_SECONDS  = 5.0
WARN_SECONDS = 8.0
TICK_MS      = 50

CHECK_HOST    = "boosteroid.com"
CHECK_PORT    = 443
CHECK_TIMEOUT = 3.0

STEPS = [
    (0.0,  "Loading…"),
    (0.4,  "Checking connection…"),
    (1.4,  "Setting up controller layout…"),
    (2.6,  "Configuring video decoder…"),
    (3.8,  "Starting Boosteroid…"),
    (4.6,  "Launching…"),
]

CSS = b"""
window { background-color: #16213e; }
#accent { background-color: #1b9fff; min-height: 4px; }
#title { color: #ffffff; font-size: 26px; font-weight: bold; }
#subtitle { color: #3d5a80; font-size: 11px; letter-spacing: 3px; }
#status { color: #4fc3f7; font-size: 12px; }
#status.warning { color: #ff9800; font-weight: bold; font-size: 13px; }
progressbar trough { background-color: #0f3460; min-height: 5px; border-radius: 3px; }
progressbar progress { background-color: #1b9fff; min-height: 5px; border-radius: 3px; }
progressbar.warning trough { background-color: #3a2a00; }
progressbar.warning progress { background-color: #ff9800; min-height: 5px; border-radius: 3px; }
"""


class SplashScreen:
    def __init__(self):
        self.elapsed  = 0.0
        self.max_time = MAX_SECONDS
        self.warned   = False

        _log("applying CSS")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        _log("creating window")
        self.win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.win.set_title("Boosteroid SteamOS")
        self.win.set_decorated(False)
        self.win.set_position(Gtk.WindowPosition.CENTER)
        self.win.set_default_size(580, 260)
        self.win.set_resizable(False)
        self.win.connect("destroy", Gtk.main_quit)

        # override_redirect: bypass the WM entirely (needed in Gamescope
        # which has no traditional window manager)
        self.win.realize()
        self.win.get_window().set_override_redirect(True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        accent = Gtk.Box()
        accent.set_name("accent")
        root.pack_start(accent, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_margin_start(56)
        content.set_margin_end(56)
        content.set_margin_top(44)
        content.set_margin_bottom(36)
        root.pack_start(content, True, True, 0)

        title = Gtk.Label(label="☁  Boosteroid SteamOS")
        title.set_name("title")
        title.set_halign(Gtk.Align.START)
        content.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label="UNOFFICIAL")
        subtitle.set_name("subtitle")
        subtitle.set_halign(Gtk.Align.START)
        content.pack_start(subtitle, False, False, 8)

        content.pack_start(Gtk.Box(), True, True, 0)

        self.status_label = Gtk.Label(label=STEPS[0][1])
        self.status_label.set_name("status")
        self.status_label.set_halign(Gtk.Align.START)
        content.pack_start(self.status_label, False, False, 10)

        self.bar = Gtk.ProgressBar()
        self.bar.set_fraction(0.0)
        content.pack_start(self.bar, False, False, 0)

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._on_sigterm)
        GLib.timeout_add(TICK_MS, self._tick)
        GLib.timeout_add(int(self.max_time * 1000), self._close)

        _log("showing window")
        self.win.show_all()
        _log("window visible")

        t = threading.Thread(target=self._check_internet, daemon=True)
        t.start()

    def _check_internet(self):
        try:
            sock = socket.create_connection((CHECK_HOST, CHECK_PORT), timeout=CHECK_TIMEOUT)
            sock.close()
            reachable = True
        except Exception:
            reachable = False
        GLib.idle_add(self._on_internet_result, reachable)

    def _on_internet_result(self, reachable):
        if not reachable and not self.warned:
            self.warned = True
            self.status_label.set_text("⚠  No internet connection — Boosteroid may not work")
            self.status_label.get_style_context().add_class("warning")
            self.bar.get_style_context().add_class("warning")
            self.max_time = WARN_SECONDS
            GLib.timeout_add(int(WARN_SECONDS * 1000), self._close)
        return False

    def _tick(self):
        self.elapsed += TICK_MS / 1000.0
        self.bar.set_fraction(min(self.elapsed / self.max_time, 1.0))
        if not self.warned:
            for t, msg in reversed(STEPS):
                if self.elapsed >= t:
                    self.status_label.set_text(msg)
                    break
        return self.elapsed < self.max_time

    def _close(self):
        self.win.destroy()
        return False

    def _on_sigterm(self):
        self._close()
        return False


def main():
    _log("calling Gtk.init_check")
    try:
        if not Gtk.init_check([])[0]:
            raise RuntimeError("Gtk.init_check returned False")
    except Exception as e:
        _log(f"cannot initialise GTK: {e}")
        sys.exit(0)
    _log("GTK initialised")

    SplashScreen()
    _log("entering Gtk.main()")
    Gtk.main()
    _log("Gtk.main() returned")
    sys.exit(0)


if __name__ == "__main__":
    main()
