#!/usr/bin/env python3
"""
Splash screen for Boosteroid SteamOS (unofficial).

Author: Schelstraete Bart
        https://github.com/bschelst/boosteroid-steamos
        https://www.schelstraete.org
"""

import csv
import sys
import os
import json
import math
import re
import socket
import threading
import time
import urllib.request
from urllib.parse import urlparse

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

STATUS_FILE   = "/tmp/.boosteroid_splash_status"

MAX_SECONDS   = 5.0    # internet OK  -> close after 5 s
WARN_SECONDS  = 10.0   # no internet  -> close after 10 s
TICK_MS       = 50
GLOW_PULSE_MS = 900    # heartbeat period per state
DOT_TICKS     = 8      # ticks between ellipsis phases (8 * 50 ms = 400 ms)

# Raw IP -- bypasses DNS so the check fails immediately when offline.
CHECK_HOST    = "1.1.1.1"
CHECK_PORT    = 53
CHECK_TIMEOUT = 3.0

LOGO_PATH  = "/app/share/boosteroid/grid/splash-logo.png"
LOGO_WIDTH = 800

GATEWAY_VERSION_URL = "https://boosteroid.schelstraete.org/api/version"
GITHUB_REPO_URL     = "https://github.com/bschelst/boosteroid-steamos"
STATS_FILE          = os.path.expanduser("~/logs/boosteroid-stats.csv")

_DOWNLOAD_URL_TEMPLATE = "https://github.com/bschelst/boosteroid-steamos/releases/download/{tag}/org.schelstraete.boosteroid.flatpak"
_SAFE_UPDATE_HOSTS = frozenset({"github.com", "objects.githubusercontent.com"})


def _is_safe_update_url(url):
    """Validate that a URL is HTTPS and from a trusted GitHub host."""
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.netloc in _SAFE_UPDATE_HOSTS
    except Exception:
        return False

# (elapsed_seconds, icon, label) -- no trailing dots; animated separately
STEPS = [
    (0.0, "\U0001f9f9", "Clearing session logs"),
    (0.6, "\U0001f310", "Testing internet connection"),
    (1.8, "\U0001f3ae", "Setting up controller layout"),
    (3.0, "\U0001f3ac", "Configuring video decoder"),
    (4.0, "\U0001f680", "Starting Boosteroid"),
    (4.7, "\u26a1",     "Launching"),
]

DOTS = ["", ".", "..", "..."]

CSS = b"""
window {
    background: linear-gradient(180deg, #0a1628 0%, #16213e 55%, #0f3460 100%);
}

#accent {
    background: linear-gradient(90deg, #0a1628, #1b9fff 35%, #1b9fff 65%, #0a1628);
    min-height: 4px;
}

#status-card {
    background-color: rgba(10, 22, 40, 0.75);
    border-radius: 12px;
    border: 1px solid rgba(27, 159, 255, 0.18);
}

#step-done { color: rgba(79, 195, 247, 0.65); font-size: 11px; }

#status { color: #4fc3f7; font-size: 13px; }
#status.warning { color: #ff9800; font-weight: bold; font-size: 14px; }

#countdown { color: rgba(27, 159, 255, 0.50); font-size: 11px; }
#countdown.warning { color: rgba(255, 152, 0, 0.60); }

#version { color: rgba(255, 255, 255, 0.70); font-size: 13px; }
#update-available { color: #ff9800; font-size: 12px; }
#update-current { color: rgba(79, 195, 247, 0.60); font-size: 12px; }
#stats { color: rgba(255, 255, 255, 0.45); font-size: 11px; }

button.update-btn {
    background: rgba(27, 159, 255, 0.25);
    color: #4fc3f7;
    border: 1px solid rgba(27, 159, 255, 0.5);
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
    text-shadow: none;
    box-shadow: none;
}
button.update-btn:hover {
    background: rgba(27, 159, 255, 0.40);
    border-color: #1b9fff;
    color: #4fc3f7;
}
button.update-btn:active {
    background: rgba(27, 159, 255, 0.60);
    border-color: #4fc3f7;
    color: white;
    padding: 9px 20px 7px 20px;
}
button.skip-btn {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.50);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
    text-shadow: none;
    box-shadow: none;
}
button.skip-btn:hover {
    background: rgba(255, 255, 255, 0.12);
    color: rgba(255, 255, 255, 0.70);
}
button.skip-btn:active {
    background: rgba(255, 255, 255, 0.20);
    color: white;
    padding: 9px 20px 7px 20px;
}

progressbar trough { background-color: #0f3460; min-height: 5px; border-radius: 3px; }
progressbar progress { background-color: #1b9fff; min-height: 5px; border-radius: 3px; }
progressbar.warning trough { background-color: #3a2a00; }
progressbar.warning progress { background-color: #ff9800; min-height: 5px; border-radius: 3px; }
"""


class SplashScreen:
    def __init__(self):
        self.elapsed         = 0.0
        self.max_time        = MAX_SECONDS
        self.warned          = False
        self._close_tid      = None
        self._net_checked    = False
        self._last_step      = f"{STEPS[0][1]}  {STEPS[0][2]}"
        self._last_step_text = STEPS[0][2]
        self._step_fade      = 1.0
        self._glow_phase     = False
        self._frame          = None
        self._dot_tick       = 0
        self._dot_phase      = 0
        self._warn_pulse     = True   # alternates warning label opacity
        self._history_box    = None
        self._history_labels = []     # pre-created; revealed on step advance
        self._history_index  = 0
        self._launcher_waiting = False

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

        # ── top spacer ────────────────────────────────────────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        # ── logo with rounded corners + shadow (Cairo-drawn) ──────────────
        logo_widget = self._make_logo()
        if logo_widget:
            logo_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            logo_hbox.pack_start(logo_widget, False, False, 0)
            logo_hbox.pack_start(Gtk.Box(), True, True, 0)
            root.pack_start(logo_hbox, False, False, 20)

        # ── gap ───────────────────────────────────────────────────────────
        gap = Gtk.Box()
        gap.set_size_request(-1, 24)
        root.pack_start(gap, False, False, 0)

        # ── status card (frosted glass, centred 700 px wide) ─────────────
        bar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(bar_hbox, False, False, 0)
        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        card = Gtk.EventBox()
        card.set_visible_window(True)
        card.set_name("status-card")
        bar_hbox.pack_start(card, False, False, 0)
        bar_hbox.pack_start(Gtk.Box(), True, True, 0)

        # Inner content: margins provide frosted-glass padding reliably
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._status_content = content
        content.set_size_request(700, -1)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(24)
        content.set_margin_end(24)
        card.add(content)

        # Completed step history — labels pre-created hidden; revealed (not added)
        # at runtime to avoid mid-animation layout thrash that causes Gamescope flashes.
        self._history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        content.pack_start(self._history_box, False, False, 0)
        for _, _, text in STEPS:
            lbl = Gtk.Label(label=f"\u2713  {text}")
            lbl.set_name("step-done")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_opacity(0.0)        # transparent but takes space: no layout shift on reveal
            self._history_box.pack_start(lbl, False, False, 0)
            self._history_labels.append(lbl)

        # Status row: spinner + label
        status_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(status_row, False, False, 10)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(14, 14)
        self.spinner.start()
        status_row.pack_start(self.spinner, False, False, 0)

        self.status_label = Gtk.Label(label=self._last_step + DOTS[0])
        self.status_label.set_name("status")
        self.status_label.set_halign(Gtk.Align.START)
        status_row.pack_start(self.status_label, False, False, 0)

        # Progress bar row: bar + countdown label
        bar_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.pack_start(bar_row, False, False, 0)

        self.bar = Gtk.ProgressBar()
        self.bar.set_pulse_step(0.02)
        self.bar.set_fraction(0.0)
        bar_row.pack_start(self.bar, True, True, 0)

        self._countdown_label = Gtk.Label(label="")
        self._countdown_label.set_name("countdown")
        self._countdown_label.set_width_chars(3)
        self._countdown_label.set_xalign(1.0)
        bar_row.pack_start(self._countdown_label, False, False, 0)

        # ── bottom spacer ─────────────────────────────────────────────────
        root.pack_start(Gtk.Box(), True, True, 0)

        # ── bottom row: version (left) · update (center) · stats (right) ──
        self._current_version = self._read_version()
        bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bottom_row.set_margin_start(40)
        bottom_row.set_margin_end(40)
        root.pack_start(bottom_row, False, False, 12)

        ver_label = Gtk.Label(label="")
        ver_label.set_name("version")
        ver_label.set_halign(Gtk.Align.START)
        if self._current_version:
            ver_label.set_text(f"v{self._current_version}  \u00b7  unofficial")
        bottom_row.pack_start(ver_label, True, True, 0)

        self._update_label = Gtk.Label(label="")
        self._update_label.set_name("update-current")
        self._update_label.set_halign(Gtk.Align.CENTER)
        self._update_label.set_opacity(0.0)
        bottom_row.pack_start(self._update_label, True, True, 0)

        stats_label = Gtk.Label(label="")
        stats_label.set_name("stats")
        stats_label.set_halign(Gtk.Align.END)
        stats_text = self._read_stats()
        if stats_text:
            stats_label.set_text(stats_text)
        bottom_row.pack_start(stats_label, True, True, 0)

        # ── timers ────────────────────────────────────────────────────────
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._on_sigterm)
        GLib.timeout_add(TICK_MS, self._tick)
        GLib.timeout_add(GLOW_PULSE_MS, self._pulse_glow)
        GLib.timeout_add(500, self._poll_launcher)
        self._close_tid = GLib.timeout_add(int(MAX_SECONDS * 1000), self._close)

        _log("showing window")
        self.win.show_all()
        _log("window visible")

        threading.Thread(target=self._check_internet, daemon=True).start()
        threading.Thread(target=self._check_update, daemon=True).start()

    # ── helpers ───────────────────────────────────────────────────────────

    def _read_version(self):
        try:
            with open("/app/share/boosteroid/version") as f:
                return f.read().strip().lstrip("v")
        except Exception:
            return ""

    @staticmethod
    def _fmt_duration(seconds):
        m = seconds // 60
        if m >= 60:
            return f"{m // 60}h {m % 60}m"
        if m > 0:
            return f"{m}m"
        return f"{seconds}s"

    @staticmethod
    def _read_stats():
        try:
            total_seconds = 0
            session_count = 0
            last_duration = 0
            launch_count = 0
            with open(STATS_FILE, newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("event") == "start":
                        launch_count += 1
                    elif row.get("event") == "end":
                        dur = int(row.get("duration_s", 0))
                        total_seconds += dur
                        last_duration = dur
                        session_count += 1
            if session_count == 0:
                if launch_count == 1:
                    return "1 session started"
                if launch_count > 1:
                    return f"{launch_count} sessions started"
                return ""
            total_str = SplashScreen._fmt_duration(total_seconds)
            last_str = SplashScreen._fmt_duration(last_duration)
            parts = [
                f"{session_count} session{'s' if session_count != 1 else ''}",
                f"total playtime {total_str}",
                f"last session {last_str}",
            ]
            return "  \u00b7  ".join(parts)
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
            _log(f"logo loaded ({orig_w}x{orig_h} -> {LOGO_WIDTH}x{new_h})")
            return Gtk.Image.new_from_pixbuf(pb)
        except Exception as e:
            _log(f"logo not loaded: {e}")
            return None

    def _add_history_step(self, _text):
        """Reveal the next history label by restoring its opacity (no layout change)."""
        if self._history_index < len(self._history_labels):
            self._history_labels[self._history_index].set_opacity(1.0)
            self._history_index += 1

    # ── launcher status file polling ──────────────────────────────────────

    def _poll_launcher(self):
        try:
            mtime = os.stat(STATUS_FILE).st_mtime
            if time.time() - mtime > 30:
                # Stale file from a crashed previous session — treat as absent
                raise FileNotFoundError
            with open(STATUS_FILE) as f:
                line = f.read().strip()
        except FileNotFoundError:
            if self._launcher_waiting:
                self._launcher_waiting = False
                # Restore the current step label (was overridden by "⏳ Waiting..." text)
                # and extend max_time so the countdown display works correctly.
                self.status_label.set_text(self._last_step + DOTS[self._dot_phase])
                self.status_label.set_opacity(1.0)
                self.max_time = self.elapsed + 3.0
                if self._close_tid is not None:
                    GLib.source_remove(self._close_tid)
                self._close_tid = GLib.timeout_add(3000, self._close)
            return True
        except Exception:
            return True

        if line.startswith("step:") and not self.warned:
            msg = line[5:]
            self._launcher_waiting = True
            self.spinner.start()
            self.spinner.show()
            self.status_label.set_text("\u23f3  " + msg)
            self.status_label.set_opacity(1.0)
            self._step_fade = 1.0
            self._countdown_label.set_text("")
            if self._close_tid is not None:
                GLib.source_remove(self._close_tid)
            # 10 s from now — covers the 4 s retry interval plus headroom
            self._close_tid = GLib.timeout_add(10000, self._close)
        elif line.startswith("warn:") and not self.warned:
            self._launcher_waiting = False
            self.warned = True
            self.spinner.stop()
            self.spinner.hide()
            self.status_label.set_text("\u26a0  " + line[5:])
            self.status_label.get_style_context().add_class("warning")
            self.bar.get_style_context().add_class("warning")
            self._countdown_label.get_style_context().add_class("warning")
            if self._close_tid is not None:
                GLib.source_remove(self._close_tid)
            self.max_time = WARN_SECONDS
            self._close_tid = GLib.timeout_add(int(WARN_SECONDS * 1000), self._close)
        return True

    # ── glow heartbeat + warning pulse ────────────────────────────────────

    def _pulse_glow(self):
        # Logo border heartbeat
        if self._frame is not None:
            ctx = self._frame.get_style_context()
            if self._glow_phase:
                ctx.remove_class("glow-b")
                ctx.add_class("glow-a")
            else:
                ctx.remove_class("glow-a")
                ctx.add_class("glow-b")
            self._glow_phase = not self._glow_phase

        # Warning icon opacity pulse
        if self.warned:
            self._warn_pulse = not self._warn_pulse
            self.status_label.set_opacity(1.0 if self._warn_pulse else 0.55)

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
                "\u26a0  No internet connection \u2014 Boosteroid may not work")
            self.status_label.get_style_context().add_class("warning")
            self.bar.get_style_context().add_class("warning")
            self._countdown_label.get_style_context().add_class("warning")
            if self._close_tid is not None:
                GLib.source_remove(self._close_tid)
            self.max_time = WARN_SECONDS
            self._close_tid = GLib.timeout_add(
                int(WARN_SECONDS * 1000), self._close)
        return False

    # ── version update check ─────────────────────────────────────────────

    @staticmethod
    def _parse_version(v):
        """Extract (major, minor, patch) tuple from a version string."""
        m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

    def _check_update(self):
        if not self._current_version:
            return
        try:
            req = urllib.request.Request(
                GATEWAY_VERSION_URL,
                headers={"User-Agent": f"boosteroid-steamos/{self._current_version}"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
            latest = data.get("latest", "")
            download_url = data.get("download_url", "")
            _log(f"update check: current=v{self._current_version} latest={latest}")
            GLib.idle_add(self._on_update_result, latest, download_url)
        except Exception as e:
            _log(f"update check failed: {e}")

    def _on_update_result(self, latest_tag, download_url):
        current = self._parse_version(self._current_version)
        latest = self._parse_version(latest_tag)
        if latest > current:
            self._update_label.set_name("update-available")
            self._update_label.set_text(
                f"\u2b06  {latest_tag} available")
            # Construct download URL from hardcoded template — never trust the gateway URL.
            self._latest_download_url = _DOWNLOAD_URL_TEMPLATE.format(tag=latest_tag)
            self._latest_tag = latest_tag
            # Pause auto-close so user can decide
            if self._close_tid is not None:
                GLib.source_remove(self._close_tid)
                self._close_tid = None
            self._show_update_prompt()
        else:
            self._update_label.set_name("update-current")
            self._update_label.set_text("\u2713  version up to date")
        self._update_label.set_opacity(1.0)
        return False

    def _show_update_prompt(self):
        """Replace status card content with update/skip buttons."""
        # Clear the status card content and shrink to fit
        for child in self._status_content.get_children():
            child.destroy()
        self._status_content.set_size_request(-1, -1)

        info = Gtk.Label(
            label=f"\u2b06  Update {self._latest_tag} is available")
        info.set_name("status")
        info.set_halign(Gtk.Align.CENTER)
        self._status_content.pack_start(info, False, False, 4)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)
        self._status_content.pack_start(btn_row, False, False, 8)

        update_btn = Gtk.Button(label="Update now")
        update_btn.get_style_context().add_class("update-btn")
        update_btn.connect("clicked", self._on_update_clicked)
        btn_row.pack_start(update_btn, False, False, 0)

        skip_btn = Gtk.Button(label="Skip")
        skip_btn.get_style_context().add_class("skip-btn")
        skip_btn.connect("clicked", self._on_skip_clicked)
        btn_row.pack_start(skip_btn, False, False, 0)

        self._status_content.show_all()

    def _on_skip_clicked(self, _btn):
        """Resume normal launch."""
        self._close_tid = GLib.timeout_add(500, self._close)

    def _on_update_clicked(self, _btn):
        """Download and install update via flatpak-spawn on host."""
        # Replace buttons with progress
        for child in self._status_content.get_children():
            child.destroy()

        self._update_status = Gtk.Label(label="\u2b07  Downloading update...")
        self._update_status.set_name("status")
        self._update_status.set_halign(Gtk.Align.CENTER)
        self._status_content.pack_start(self._update_status, False, False, 4)

        self._update_bar = Gtk.ProgressBar()
        self._update_bar.set_pulse_step(0.03)
        self._status_content.pack_start(self._update_bar, False, False, 4)
        self._status_content.show_all()

        self._update_pulse_tid = GLib.timeout_add(80, self._pulse_update_bar)
        threading.Thread(target=self._do_update, daemon=True).start()

    def _pulse_update_bar(self):
        if hasattr(self, '_update_bar'):
            self._update_bar.pulse()
        return True

    def _do_update(self):
        """Download + install in background thread using flatpak-spawn."""
        import subprocess
        tmp_path = "/tmp/boosteroid-update.flatpak"
        try:
            if not _is_safe_update_url(self._latest_download_url):
                raise RuntimeError(
                    f"blocked unsafe update URL: {self._latest_download_url}")
            # Download on host via flatpak-spawn
            _log(f"downloading update from {self._latest_download_url}")
            r = subprocess.run(
                ["flatpak-spawn", "--host", "curl", "-fsSL",
                 "-o", tmp_path, self._latest_download_url],
                capture_output=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f"download failed: {r.stderr.decode()}")

            GLib.idle_add(self._update_status.set_text,
                          "\u2699  Installing update...")

            # Install on host
            _log("installing update")
            r = subprocess.run(
                ["flatpak-spawn", "--host", "flatpak", "install",
                 "--user", "-y", tmp_path],
                capture_output=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError(f"install failed: {r.stderr.decode()}")

            # Cleanup
            subprocess.run(
                ["flatpak-spawn", "--host", "rm", "-f", tmp_path],
                capture_output=True, timeout=10)

            _log("update installed successfully")
            GLib.idle_add(self._on_update_complete, True, "")
        except Exception as e:
            _log(f"update failed: {e}")
            GLib.idle_add(self._on_update_complete, False, str(e))

    def _on_update_complete(self, success, error):
        if hasattr(self, '_update_pulse_tid'):
            GLib.source_remove(self._update_pulse_tid)
        if success:
            self._update_status.set_text(
                f"\u2713  Updated to {self._latest_tag}! Launching...")
            self._update_bar.set_fraction(1.0)
            self._close_tid = GLib.timeout_add(2000, self._close)
        else:
            self._update_status.set_text(
                f"\u26a0  Update failed — launching current version")
            self._update_status.get_style_context().add_class("warning")
            self._close_tid = GLib.timeout_add(3000, self._close)
        return False

    # ── per-tick update ───────────────────────────────────────────────────

    def _tick(self):
        self.elapsed += TICK_MS / 1000.0

        # Progress bar + countdown
        if self._launcher_waiting:
            self.bar.pulse()
            self._countdown_label.set_text("")
        elif not self._net_checked:
            self.bar.pulse()
            self._countdown_label.set_text("")
        else:
            self.bar.set_fraction(min(self.elapsed / self.max_time, 1.0))
            remaining = max(1, math.ceil(self.max_time - self.elapsed))
            self._countdown_label.set_text(f"{remaining}s")

        # Advance step + history (not in warning mode)
        if not self.warned:
            for t, icon, text in reversed(STEPS):
                if self.elapsed >= t:
                    display = f"{icon}  {text}"
                    if display != self._last_step:
                        self._add_history_step(self._last_step_text)
                        self._last_step      = display
                        self._last_step_text = text
                        self._step_fade      = 0.0
                        self._dot_tick       = 0
                        self._dot_phase      = 0
                        self.status_label.set_opacity(0.0)
                        self.status_label.set_text(display + DOTS[0])
                    break

            # Animated ellipsis
            self._dot_tick += 1
            if self._dot_tick >= DOT_TICKS:
                self._dot_tick  = 0
                self._dot_phase = (self._dot_phase + 1) % len(DOTS)
                if self._step_fade >= 1.0:
                    self.status_label.set_text(
                        self._last_step + DOTS[self._dot_phase])

        # Fade in new step text
        if self._step_fade < 1.0:
            self._step_fade = min(1.0, self._step_fade + 0.18)
            self.status_label.set_opacity(self._step_fade)

        # Always return True — close is driven exclusively by _close_tid.
        # Returning False here would freeze the display if elapsed > max_time
        # while the launcher-wait state kept the splash alive past max_time.
        return True

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
