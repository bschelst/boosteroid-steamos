#!/usr/bin/env python3
"""
First-run installer: downloads the official Boosteroid .deb from boosteroid.com
and extracts it into $XDG_DATA_HOME/boosteroid/ using Python stdlib only.

Author: Schelstraete Bart
        https://github.com/bschelst/boosteroid-steamos
        https://www.schelstraete.org
"""

import hashlib
import io
import os
import sys
import tarfile
import urllib.error
import urllib.request

DEB_URL = "https://boosteroid.com/linux/installer/boosteroid-install-x64.deb"
MD5_URL = "https://boosteroid.com/linux/installer/boosteroid-install-x64.deb.md5"


def _reporthook(count, block_size, total_size):
    if total_size > 0:
        pct = min(count * block_size * 100 // total_size, 100)
        print(f"\r  {pct}% ", end="", flush=True)


def download_file(url, dest_path):
    print(f"Downloading {url}")
    urllib.request.urlretrieve(url, dest_path, _reporthook)
    print()


def verify_md5(file_path, md5_url):
    try:
        with urllib.request.urlopen(md5_url) as resp:
            expected = resp.read().decode().split()[0]
    except urllib.error.HTTPError as exc:
        print(f"  MD5 check skipped ({exc.code} from server)")
        return
    with open(file_path, "rb") as f:
        actual = hashlib.md5(f.read()).hexdigest()
    if expected != actual:
        raise RuntimeError(f"MD5 mismatch: expected {expected}, got {actual}")
    print("  MD5 OK")


def _extract_ar_member(deb_path, prefix):
    """Return bytes of the first ar member whose name starts with `prefix`."""
    with open(deb_path, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            raise ValueError("Not a valid .deb (ar magic missing)")
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[0:16].rstrip(b" /").decode("ascii", errors="replace")
            size = int(header[48:58].strip())
            data = f.read(size)
            if size % 2:
                f.read(1)  # ar padding byte
            if name.startswith(prefix):
                return data
    raise ValueError(f"No ar member matching '{prefix}' in {deb_path}")


def extract_deb(deb_path, target_dir):
    """Extract data.tar.* from a .deb into target_dir."""
    raw = _extract_ar_member(deb_path, "data.tar")
    magic = raw[:6]
    if magic[:2] == b"\x1f\x8b":
        mode = "r:gz"
    elif magic == b"\xfd7zXZ\x00":
        mode = "r:xz"
    elif magic[:3] == b"BZh":
        mode = "r:bz2"
    else:
        mode = "r:"
    with tarfile.open(fileobj=io.BytesIO(raw), mode=mode) as tar:
        # filter="data" (Python 3.12+) strips dangerous paths and prevents
        # path-traversal entries. Fall back to unfiltered on older Pythons.
        if sys.version_info >= (3, 12):
            tar.extractall(target_dir, filter="data")
        else:
            tar.extractall(target_dir)  # noqa: S202
    print(f"  Extracted to {target_dir}")


def main():
    xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    install_dir = os.path.join(xdg_data, "boosteroid")
    binary = os.path.join(install_dir, "opt", "BoosteroidGamesS.R.L.", "bin", "Boosteroid")

    if os.path.isfile(binary):
        print("Boosteroid already installed.")
        return

    os.makedirs(install_dir, exist_ok=True)
    deb_path = os.path.join(install_dir, "boosteroid.deb")

    download_file(DEB_URL, deb_path)
    print("Verifying...")
    verify_md5(deb_path, MD5_URL)
    print("Extracting...")
    extract_deb(deb_path, install_dir)
    os.unlink(deb_path)
    print("Done.")


if __name__ == "__main__":
    main()
