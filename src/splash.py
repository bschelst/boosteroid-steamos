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
    from gi.repository import Gtk, GLib, Gdk, GdkPixbuf
    _log("Gtk imported")
except Exception as e:
    _log(f"GTK unavailable, skipping: {e}")
    sys.exit(0)

MAX_SECONDS  = 10.0
WARN_SECONDS = MAX_SECONDS + 4.0
TICK_MS      = 50

# Use a raw IP to bypass DNS — when internet is down, DNS resolution can
# hang far longer than any socket timeout, causing the check to return only
# after the splash is gone.  Cloudflare 1.1.1.1:53 is a reliable target.
CHECK_HOST    = "1.1.1.1"
CHECK_PORT    = 53
CHECK_TIMEOUT = 3.0

LOGO_PATH  = "/app/share/boosteroid/grid/wide.png"
LOGO_WIDTH = 800   # scaled width; height is derived from aspect ratio

STEPS = [
    (0.0,  "Testing internet connection…"),
    (3.5,  "Setting up controller layout…"),
    (6.0,  "Configuring video decoder…"),
    (8.0,  "Starting Boosteroid…"),
    (9.2,  "Launching…"),
]

CSS = b"""
window { background-color: #16213e; }
#accent { background-color: #1b9fff; min-height: 4px; }
#status { color: #4fc3f7; font-size: 13px; }
#status.warning { color: #ff9800; font-weight: bold; font-size: 14px; }
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
        self.win.set_resizable(False)
        self.win.connect("destroy", Gtk.main_quit)

        # Gamescope (Game Mode) only composites fullscreen X11 windows.
        # Request fullscreen before show_all() so it is set when the window maps.
        self.win.fullscreen()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        # ── top accent bar ────────────────────────────────────────────────
        accent = Gtk.Box()
        accent.set_name("accent")
        root.pack_start(accent, False, False, 0)

        # ── top spacer (pushes content to vertical centre) ────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        # ── logo image (centred horizontally) ─────────────────────────────
        logo_widget = self._make_logo()
        if logo_widget:
            logo_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            logo_hbox.pack_start(logo_widget, False, False, 0)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            root.pack_start(logo_hbox, False, False, 0)

        # ── gap between logo and status row ──────────────────────────────
        gap = Gtk.Box()
        gap.set_size_request(-1, 28)
        root.pack_start(gap, False, False, 0)

        # ── status label + progress bar (centred, 700 px wide) ───────────
        bar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(bar_hbox, False, False, 0)

        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_size_request(700, -1)
        bar_hbox.pack_start(content, False, False, 0)

        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        self.status_label = Gtk.Label(label=STEPS[0][1])
        self.status_label.set_name("status")
        self.status_label.set_halign(Gtk.Align.START)
        content.pack_start(self.status_label, False, False, 10)

        self.bar = Gtk.ProgressBar()
        self.bar.set_fraction(0.0)
        content.pack_start(self.bar, False, False, 0)

        # ── bottom spacer ─────────────────────────────────────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._on_sigterm)
        GLib.timeout_add(TICK_MS, self._tick)
        GLib.timeout_add(int(self.max_time * 1000), self._close)

        _log("showing window")
        self.win.show_all()
        _log("window visible")

        t = threading.Thread(target=self._check_internet, daemon=True)
        t.start()

    def _make_logo(self):
        try:
            pb_orig = GdkPixbuf.Pixbuf.new_from_file(LOGO_PATH)
            orig_w  = pb_orig.get_width()
            orig_h  = pb_orig.get_height()
            new_h   = int(orig_h * LOGO_WIDTH / orig_w)
            pb      = pb_orig.scale_simple(LOGO_WIDTH, new_h,
                                           GdkPixbuf.InterpType.BILINEAR)
            _log(f"logo loaded ({orig_w}x{orig_h} → {LOGO_WIDTH}x{new_h})")
            return Gtk.Image.new_from_pixbuf(pb)
        except Exception as e:
            _log(f"logo not loaded: {e}")
            return None

    def _check_internet(self):
        try:
            sock = socket.create_connection((CHECK_HOST, CHECK_PORT),
                                            timeout=CHECK_TIMEOUT)
            sock.close()
            reachable = True
        except Exception as e:
            _log(f"internet check failed: {e}")
            reachable = False
        _log(f"internet reachable: {reachable}")
        GLib.idle_add(self._on_internet_result, reachable)

    def _on_internet_result(self, reachable):
        if not reachable and not self.warned:
            self.warned = True
            self.status_label.set_text(
                "⚠  No internet connection — Boosteroid may not work")
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
