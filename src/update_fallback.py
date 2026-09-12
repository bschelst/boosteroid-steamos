#!/usr/bin/env python3
"""Channel-following .deb fallback for stale Boosteroid flatpak bundles.

Boosteroid's Linux client updates itself by downloading a .flatpak bundle for
the channel the user selected in its settings (stable, or "latest" = beta).
Sometimes Boosteroid publishes a new version to Updates.xml and to the .deb
installer but forgets to rebuild the bundle.  The client then loops forever:
download bundle -> install same old version -> prompt for the update again.

The launcher runs this script AFTER the bundle's binary has been copied into
place.  It never guesses the channel: it reads the bundle URL Boosteroid just
downloaded from Boosteroid's own log and derives the matching Updates.xml and
.deb URLs from it.  If the installed binary is older than what that channel
advertises, the channel's .deb is downloaded and installed over the tree.

One attempt per (channel, remote version) is recorded so a .deb that is also
stale does not trigger an 80 MB download on every launch.  A new remote
version resets that guard.  Once Boosteroid ships a correct bundle the version
check passes and this script is a no-op.

Stdlib only -- runs inside the Flatpak sandbox.
"""

import argparse
import collections
import mmap
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import install_boosteroid

BINARY_REL = "opt/BoosteroidGamesS.R.L./bin/Boosteroid"
STATE_FILE = ".deb-fallback-attempted"
ALLOWED_HOST = "boosteroid.com"
DEB_NAME = "boosteroid-install-x64.deb"
# boosteroid.com returns 403 for curl's default UA; a browser-style UA is accepted.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) BoosteroidSteamOS"
HTTP_TIMEOUT = 20
# Sanity caps: Updates.xml is a few KB, the .deb is ~80 MB.  Anything far beyond
# that is not a Boosteroid release and must not be allowed to fill the disk.
MAX_XML_BYTES = 4 << 20
MAX_DEB_BYTES = 500 << 20

_BUNDLE_RE = re.compile(r'Downloading update archive from "(https?://[^"]+)"')
_VERSION_RE = re.compile(rb"(\d+\.\d+\.\d+) \(([A-Za-z]+)\)")

ChannelUrls = collections.namedtuple("ChannelUrls", "name updates_xml deb")


def log(msg):
    print(f"[deb-fallback] {msg}", flush=True)


def find_bundle_url(log_text):
    """Return the URL of the last bundle Boosteroid downloaded, or None."""
    matches = _BUNDLE_RE.findall(log_text)
    return matches[-1] if matches else None


def channel_urls(bundle_url):
    """Derive Updates.xml and .deb URLs for the channel a bundle URL belongs to.

    installer/latest/Boosteroid.flatpak -> client/latest/Updates.xml (beta)
    installer/Boosteroid.flatpak        -> client/Updates.xml        (stable)
    """
    parsed = urllib.parse.urlsplit(bundle_url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise ValueError(f"bundle URL is not https://{ALLOWED_HOST}/...: {bundle_url}")
    base = parsed.path.rsplit("/", 1)[0] + "/"
    if "/installer/" not in base:
        raise ValueError(f"unexpected bundle path: {bundle_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    last_dir = base.rstrip("/").rsplit("/", 1)[-1]
    name = "stable" if last_dir == "installer" else last_dir
    return ChannelUrls(
        name=name,
        updates_xml=origin + base.replace("/installer/", "/client/", 1) + "Updates.xml",
        deb=origin + base + DEB_NAME,
    )


def parse_version(text):
    m = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def format_version(v):
    return ".".join(str(x) for x in v)


def binary_version(path):
    """Most common 'X.Y.Z (Tag)' string in the binary, ignoring Qt's own version.

    NOTE: the tag is '(Beta)' on BOTH channels -- it says nothing about the
    channel, only the numeric part is meaningful.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return None
    counts = collections.Counter()
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for ver, tag in _VERSION_RE.findall(mm):
            if tag != b"Qt":
                counts[ver.decode()] += 1
    if not counts:
        return None
    return parse_version(counts.most_common(1)[0][0])


def parse_updates_xml(data):
    """<Version> of the PackageUpdate named 'Boosteroid', or None."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    for pkg in root.iter("PackageUpdate"):
        if pkg.findtext("Name") == "Boosteroid":
            return parse_version(pkg.findtext("Version"))
    return None


def _open(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    resp = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
    length = resp.headers.get("Content-Length")
    if length and int(length) > limit:
        resp.close()
        raise ValueError(f"{url} is {length} bytes, over the {limit} byte limit")
    return resp


def fetch(url):
    with _open(url, MAX_XML_BYTES) as resp:
        data = resp.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError(f"{url} exceeds the {MAX_XML_BYTES} byte limit")
    return data


def download(url, dest):
    written = 0
    with _open(url, MAX_DEB_BYTES) as resp, open(dest, "wb") as out:
        while chunk := resp.read(1 << 20):
            written += len(chunk)
            if written > MAX_DEB_BYTES:
                raise ValueError(f"{url} exceeds the {MAX_DEB_BYTES} byte limit")
            out.write(chunk)


def state_path(install_dir):
    return Path(install_dir) / STATE_FILE


def read_state(install_dir):
    try:
        return state_path(install_dir).read_text().strip()
    except OSError:
        return ""


def write_state(install_dir, key):
    path = state_path(install_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(key + "\n")
    os.replace(tmp, path)


def decide(local, remote, attempted_key, key):
    if local >= remote:
        return "up-to-date"
    if attempted_key == key:
        return "already-attempted"
    return "fallback"


def install_deb(deb_path, install_dir, local, extract):
    """Extract the .deb next to install_dir, verify it is newer, swap it in.

    The swap is two renames on the same filesystem, so the install tree is
    always either the complete old release or the complete new one -- never a
    mix, even if the Deck is powered off half-way through.

    Returns the installed version, or None if the .deb was not newer than
    what is already installed (nothing is changed in that case).
    """
    install_dir = Path(install_dir)
    staging = Path(tempfile.mkdtemp(prefix=install_dir.name + ".new", dir=install_dir.parent))
    backup = install_dir.with_name(install_dir.name + ".old")
    try:
        extract(str(deb_path), str(staging))
        new = binary_version(staging / BINARY_REL)
        if new is None or new <= local:
            log(f"the .deb contains {format_version(new) if new else 'no readable version'} "
                f"-- not newer than installed {format_version(local)}, leaving install untouched")
            return None
        log(f"installing {format_version(new)} over {install_dir}")
        shutil.rmtree(backup, ignore_errors=True)
        os.replace(install_dir, backup)
        try:
            os.replace(staging, install_dir)
        except OSError:
            os.replace(backup, install_dir)
            raise
        return new
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def run(log_path, install_dir, dry_run, fetch=fetch, download=download,
        extract=install_boosteroid.extract_deb):
    """Always returns 0 -- the launcher must never fail because of this check."""
    install_dir = Path(install_dir)
    try:
        log_text = Path(log_path).read_text(errors="replace")
    except OSError as exc:
        log(f"cannot read Boosteroid log ({exc}); nothing to do")
        return 0

    bundle_url = find_bundle_url(log_text)
    if not bundle_url:
        log("no bundle download in Boosteroid log; nothing to do")
        return 0
    try:
        ch = channel_urls(bundle_url)
    except ValueError as exc:
        log(f"ignoring bundle URL: {exc}")
        return 0

    local = binary_version(install_dir / BINARY_REL)
    if local is None:
        log("cannot read installed binary version; nothing to do")
        return 0
    try:
        remote = parse_updates_xml(fetch(ch.updates_xml))
    except OSError as exc:
        log(f"cannot fetch {ch.updates_xml} ({exc}); nothing to do")
        return 0
    if remote is None:
        log(f"no Boosteroid version in {ch.updates_xml}; nothing to do")
        return 0

    key = f"{ch.name}:{format_version(remote)}"
    verdict = decide(local, remote, read_state(install_dir), key)
    log(f"channel={ch.name} installed={format_version(local)} "
        f"advertised={format_version(remote)} -> {verdict}")
    if verdict != "fallback":
        return 0
    log(f"bundle for channel '{ch.name}' is stale; using {ch.deb}")
    if dry_run:
        log("dry run -- not downloading")
        return 0

    with tempfile.TemporaryDirectory(prefix="deb-fallback-", dir=install_dir.parent) as tmp:
        deb_path = Path(tmp) / DEB_NAME
        try:
            log(f"downloading {ch.deb} ...")
            download(ch.deb, deb_path)
        except (OSError, ValueError) as exc:
            # Transient (offline, CDN hiccup): leave the guard unset so the
            # next launch retries.
            log(f"download failed: {exc}")
            return 0
        installed = None
        try:
            installed = install_deb(deb_path, install_dir, local, extract)
        except (OSError, ValueError, RuntimeError, tarfile.TarError) as exc:
            log(f"install failed: {exc}")
        # Record the attempt whether the .deb was newer, stale or broken: it
        # must not be re-downloaded until Boosteroid advertises a new version.
        try:
            write_state(install_dir, key)
        except OSError as exc:
            log(f"cannot record attempt ({exc})")
    if installed:
        log(f"now at {format_version(installed)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the channel's .deb when Boosteroid's flatpak bundle is stale")
    parser.add_argument("--log", required=True, help="path to Boosteroid's bstr_client.log")
    parser.add_argument("--install-dir", required=True, help="dir containing opt/BoosteroidGamesS.R.L.")
    parser.add_argument("--dry-run", action="store_true", help="report the decision, change nothing")
    args = parser.parse_args(argv)
    return run(args.log, args.install_dir, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
