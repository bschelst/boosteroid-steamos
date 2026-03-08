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

MAX_SECONDS   = 5.0    # internet OK  → close after 5 s
WARN_SECONDS  = 10.0   # no internet  → close after 10 s
TICK_MS       = 50
GLOW_PULSE_MS = 900    # heartbeat period per state

# Raw IP — bypasses DNS so the check fails immediately when offline.
CHECK_HOST    = "1.1.1.1"
CHECK_PORT    = 53
CHECK_TIMEOUT = 3.0

LOGO_PATH  = "/app/share/boosteroid/grid/wide.png"
LOGO_WIDTH = 800

STEPS = [
    (0.0,  "Testing internet connection…"),
    (1.5,  "Setting up controller layout…"),
    (3.0,  "Configuring video decoder…"),
    (4.0,  "Starting Boosteroid…"),
    (4.7,  "Launching…"),
]

CSS = b"""
window {
    background: linear-gradient(180deg, #0a1628 0%, #16213e 55%, #0f3460 100%);
}
#accent { background-color: #1b9fff; min-height: 4px; }

/* Glowing logo border — two states toggled for heartbeat pulse */
#logo-frame {
    border-radius: 8px;
    border: 1px solid #1b9fff;
    padding: 4px;
}
#logo-frame.glow-a {
    box-shadow:
        0 0  8px #1b9fff,
        0 0 20px rgba(27, 159, 255, 0.55),
        0 0 42px rgba(27, 159, 255, 0.25),
        0 0 64px rgba(27, 159, 255, 0.10);
}
#logo-frame.glow-b {
    box-shadow:
        0 0 14px #1b9fff,
        0 0 36px rgba(27, 159, 255, 0.90),
        0 0 65px rgba(27, 159, 255, 0.55),
        0 0 95px rgba(27, 159, 255, 0.25);
}

#status { color: #4fc3f7; font-size: 13px; }
#status.warning { color: #ff9800; font-weight: bold; font-size: 14px; }

#version { color: #1e3a5f; font-size: 10px; }

progressbar trough { background-color: #0f3460; min-height: 5px; border-radius: 3px; }
progressbar progress { background-color: #1b9fff; min-height: 5px; border-radius: 3px; }
progressbar.warning trough { background-color: #3a2a00; }
progressbar.warning progress { background-color: #ff9800; min-height: 5px; border-radius: 3px; }
"""


class SplashScreen:
    def __init__(self):
        self.elapsed       = 0.0
        self.max_time      = MAX_SECONDS
        self.warned        = False
        self._close_tid    = None
        self._net_checked  = False   # becomes True when check result arrives
        self._last_step    = STEPS[0][1]  # track current step to detect changes
        self._step_fade    = 1.0     # 0..1 opacity used to fade in new step text
        self._glow_phase   = False   # alternates between glow-a / glow-b
        self._frame        = None    # EventBox for the logo (needed for glow pulse)

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
        self.win.fullscreen()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win.add(root)

        # ── top accent bar ────────────────────────────────────────────────
        accent = Gtk.Box()
        accent.set_name("accent")
        root.pack_start(accent, False, False, 0)

        # ── version label pinned to bottom ────────────────────────────────
        version = self._read_version()
        if version:
            ver_label = Gtk.Label(label=f"v{version}  ·  unofficial")
            ver_label.set_name("version")
            root.pack_end(ver_label, False, False, 14)

        # ── top spacer (centres logo+status vertically) ───────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        # ── logo with glowing frame ───────────────────────────────────────
        logo_widget = self._make_logo()
        if logo_widget:
            self._frame = Gtk.EventBox()
            self._frame.set_visible_window(True)
            self._frame.set_name("logo-frame")
            self._frame.get_style_context().add_class("glow-a")
            self._frame.add(logo_widget)

            logo_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            logo_hbox.pack_start(self._frame, False, False, 0)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            # 20 px top/bottom padding so the outer glow is not clipped
            root.pack_start(logo_hbox, False, False, 20)

        # ── gap between logo and status row ──────────────────────────────
        gap = Gtk.Box()
        gap.set_size_request(-1, 24)
        root.pack_start(gap, False, False, 0)

        # ── status + progress bar (centred, 700 px wide) ──────────────────
        bar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(bar_hbox, False, False, 0)
        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_size_request(700, -1)
        bar_hbox.pack_start(content, False, False, 0)
        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        # Status row: spinner + label side by side
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(status_row, False, False, 10)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(14, 14)
        self.spinner.start()
        status_row.pack_start(self.spinner, False, False, 0)

        self.status_label = Gtk.Label(label=STEPS[0][1])
        self.status_label.set_name("status")
        self.status_label.set_halign(Gtk.Align.START)
        status_row.pack_start(self.status_label, False, False, 0)

        self.bar = Gtk.ProgressBar()
        self.bar.set_pulse_step(0.02)
        self.bar.set_fraction(0.0)
        content.pack_start(self.bar, False, False, 0)

        # ── bottom spacer ─────────────────────────────────────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        # ── timers ────────────────────────────────────────────────────────
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._on_sigterm)
        GLib.timeout_add(TICK_MS, self._tick)
        GLib.timeout_add(GLOW_PULSE_MS, self._pulse_glow)
        self._close_tid = GLib.timeout_add(int(MAX_SECONDS * 1000), self._close)

        _log("showing window")
        self.win.show_all()
        _log("window visible")

        threading.Thread(target=self._check_internet, daemon=True).start()

    # ── helpers ───────────────────────────────────────────────────────────

    def _read_version(self):
        try:
            with open("/app/share/boosteroid/version") as f:
                return f.read().strip()
        except Exception:
            return ""

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

    # ── glow heartbeat ────────────────────────────────────────────────────

    def _pulse_glow(self):
        if self._frame is None:
            return True
        ctx = self._frame.get_style_context()
        if self._glow_phase:
            ctx.remove_class("glow-b")
            ctx.add_class("glow-a")
        else:
            ctx.remove_class("glow-a")
            ctx.add_class("glow-b")
        self._glow_phase = not self._glow_phase
        return True

    # ── internet check ────────────────────────────────────────────────────

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
        self._net_checked = True
        self.spinner.stop()
        self.spinner.hide()
        if not reachable and not self.warned:
            self.warned = True
            self.status_label.set_opacity(1.0)
            self.status_label.set_text(
                "⚠  No internet connection — Boosteroid may not work")
            self.status_label.get_style_context().add_class("warning")
            self.bar.get_style_context().add_class("warning")
            if self._close_tid is not None:
                GLib.source_remove(self._close_tid)
            self.max_time = WARN_SECONDS
            self._close_tid = GLib.timeout_add(
                int(WARN_SECONDS * 1000), self._close)
        return False

    # ── per-tick update ───────────────────────────────────────────────────

    def _tick(self):
        self.elapsed += TICK_MS / 1000.0

        # Progress bar: indeterminate pulse while waiting for internet check,
        # then deterministic fill once the result is in.
        if not self._net_checked:
            self.bar.pulse()
        else:
            self.bar.set_fraction(min(self.elapsed / self.max_time, 1.0))

        # Advance step text
        if not self.warned:
            for t, msg in reversed(STEPS):
                if self.elapsed >= t:
                    if msg != self._last_step:
                        self._last_step = msg
                        self._step_fade = 0.0
                        self.status_label.set_opacity(0.0)
                        self.status_label.set_text(msg)
                    break

        # Fade new step text in
        if self._step_fade < 1.0:
            self._step_fade = min(1.0, self._step_fade + 0.18)
            self.status_label.set_opacity(self._step_fade)

        return self.elapsed < self.max_time

    # ── close / signal ────────────────────────────────────────────────────

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
