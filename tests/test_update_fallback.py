#!/usr/bin/env python3
"""Unit tests for src/update_fallback.py (stdlib unittest, no network)."""

import io
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import update_fallback as uf  # noqa: E402

BETA_URL = "https://boosteroid.com/linux/installer/latest/Boosteroid.flatpak?1789225418"
STABLE_URL = "https://boosteroid.com/linux/installer/Boosteroid.flatpak?1789225500"

LOG_BETA = f"""
[2026-09-12 17:02:11.000] [file_logger] [debug] [   Update Controller]: Starting updater, current version:  stable , downloading version:  latest
[2026-09-12 17:02:11.001] [file_logger] [info] [    Platform Updater]: Downloading update archive from "{STABLE_URL}" to "/x/Boosteroid.flatpak"
[2026-09-12 17:03:38.701] [file_logger] [info] [    Platform Updater]: Downloading update archive from "{BETA_URL}" to "/x/Boosteroid.flatpak"
[2026-09-12 17:03:57.873] [file_logger] [debug] [    Platform Updater]: Download finished with result: 0 HTTP: 200
"""

UPDATES_XML = b"""<Updates>
 <PackageUpdate>
  <Name>Crash Handler</Name>
  <Version>9.9.9</Version>
 </PackageUpdate>
 <PackageUpdate>
  <Name>Boosteroid</Name>
  <Version>1.11.24</Version>
 </PackageUpdate>
</Updates>"""


def fake_binary(path, *versions):
    """Write a file that mimics the version strings embedded in the real binary."""
    body = b"\x00junk 1.3.1 (Qt)\x00" + b"".join(
        f"\x00{v} (Beta)\x00".encode() for v in versions
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _ar_member(name, data):
    header = f"{name:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n".encode()
    return header + data + (b"\n" if len(data) % 2 else b"")


def build_deb(version, escape=False):
    """Build a minimal but genuine .deb (ar + data.tar.gz) in memory.

    With escape=True the tar carries a symlink pointing outside the target
    directory, which tarfile's "data" filter must reject.
    """
    with tempfile.TemporaryDirectory() as td:
        tree = Path(td)
        fake_binary(tree / uf.BINARY_REL, version)
        (tree / "opt" / "readme.txt").write_text("hello")
        os.symlink("readme.txt", tree / "opt" / "link.txt")
        if escape:
            os.symlink("../../../escaped", tree / "opt" / "evil.txt")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(tree, arcname=".")
    return (b"!<arch>\n" + _ar_member("debian-binary", b"2.0\n")
            + _ar_member("control.tar.gz", b"") + _ar_member("data.tar.gz", buf.getvalue()))


class LogParsing(unittest.TestCase):
    def test_returns_last_bundle_url(self):
        self.assertEqual(uf.find_bundle_url(LOG_BETA), BETA_URL)

    def test_none_when_no_download_logged(self):
        self.assertIsNone(uf.find_bundle_url("nothing here\n"))


class ChannelUrls(unittest.TestCase):
    def test_beta_channel(self):
        ch = uf.channel_urls(BETA_URL)
        self.assertEqual(ch.name, "latest")
        self.assertEqual(ch.updates_xml, "https://boosteroid.com/linux/client/latest/Updates.xml")
        self.assertEqual(ch.deb, "https://boosteroid.com/linux/installer/latest/boosteroid-install-x64.deb")

    def test_stable_channel(self):
        ch = uf.channel_urls(STABLE_URL)
        self.assertEqual(ch.name, "stable")
        self.assertEqual(ch.updates_xml, "https://boosteroid.com/linux/client/Updates.xml")
        self.assertEqual(ch.deb, "https://boosteroid.com/linux/installer/boosteroid-install-x64.deb")

    def test_rejects_non_boosteroid_host(self):
        with self.assertRaises(ValueError):
            uf.channel_urls("https://evil.example/linux/installer/Boosteroid.flatpak")


class Versions(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(uf.parse_version("1.11.24"), (1, 11, 24))
        self.assertIsNone(uf.parse_version("garbage"))

    def test_binary_version_ignores_qt_and_picks_most_common(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Boosteroid"
            fake_binary(p, "1.11.22", "1.11.22", "1.11.24")
            self.assertEqual(uf.binary_version(p), (1, 11, 22))

    def test_binary_version_none_when_absent(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Boosteroid"
            p.write_bytes(b"\x00no version here 1.3.1 (Qt)\x00")
            self.assertIsNone(uf.binary_version(p))
            self.assertIsNone(uf.binary_version(Path(td) / "missing"))

    def test_updates_xml_picks_boosteroid_package(self):
        self.assertEqual(uf.parse_updates_xml(UPDATES_XML), (1, 11, 24))

    def test_updates_xml_invalid(self):
        self.assertIsNone(uf.parse_updates_xml(b"<not xml"))
        self.assertIsNone(uf.parse_updates_xml(b"<Updates/>"))


class Decision(unittest.TestCase):
    def test_up_to_date(self):
        self.assertEqual(uf.decide((1, 11, 24), (1, 11, 24), "", "latest:1.11.24"), "up-to-date")
        self.assertEqual(uf.decide((1, 11, 25), (1, 11, 24), "", "latest:1.11.24"), "up-to-date")

    def test_already_attempted(self):
        self.assertEqual(
            uf.decide((1, 11, 22), (1, 11, 24), "latest:1.11.24", "latest:1.11.24"),
            "already-attempted",
        )

    def test_fallback_needed(self):
        self.assertEqual(uf.decide((1, 11, 20), (1, 11, 24), "", "latest:1.11.24"), "fallback")
        # A new remote version resets the attempt guard.
        self.assertEqual(
            uf.decide((1, 11, 22), (1, 11, 26), "latest:1.11.24", "latest:1.11.26"), "fallback"
        )


class InstallDeb(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.install_dir = self.root / "boosteroid"
        fake_binary(self.install_dir / uf.BINARY_REL, "1.11.22")

    def tearDown(self):
        self._td.cleanup()

    def _extractor(self, version):
        def extract(deb_path, target_dir):
            fake_binary(Path(target_dir) / uf.BINARY_REL, version)
            (Path(target_dir) / "opt" / "extra.txt").write_text("new file")
        return extract

    def test_installs_newer_tree(self):
        got = uf.install_deb(self.root / "x.deb", self.install_dir, (1, 11, 22), self._extractor("1.11.24"))
        self.assertEqual(got, (1, 11, 24))
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 24))
        self.assertTrue((self.install_dir / "opt" / "extra.txt").exists())
        self.assertFalse(list(self.root.glob("boosteroid.new*")), "staging dir not cleaned up")

    def test_rejects_stale_deb(self):
        got = uf.install_deb(self.root / "x.deb", self.install_dir, (1, 11, 22), self._extractor("1.11.22"))
        self.assertIsNone(got)
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 22))
        self.assertFalse((self.install_dir / "opt" / "extra.txt").exists())
        self.assertFalse(list(self.root.glob("boosteroid.new*")))

    def test_swap_replaces_whole_tree(self):
        # Files dropped by the new release must not linger, and no .old dir may remain.
        (self.install_dir / "opt" / "obsolete.so").write_text("old lib")
        uf.install_deb(self.root / "x.deb", self.install_dir, (1, 11, 22), self._extractor("1.11.24"))
        self.assertFalse((self.install_dir / "opt" / "obsolete.so").exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["boosteroid"])

    def test_failed_extraction_leaves_install_untouched(self):
        def extract(deb_path, target_dir):
            fake_binary(Path(target_dir) / uf.BINARY_REL, "1.11.24")
            raise tarfile.TarError("truncated")
        with self.assertRaises(tarfile.TarError):
            uf.install_deb(self.root / "x.deb", self.install_dir, (1, 11, 22), extract)
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 22))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["boosteroid"])

    def test_real_deb_extractor(self):
        deb = self.root / "real.deb"
        deb.write_bytes(build_deb("1.11.24"))
        got = uf.install_deb(deb, self.install_dir, (1, 11, 22), uf.install_boosteroid.extract_deb)
        self.assertEqual(got, (1, 11, 24))
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 24))
        self.assertTrue((self.install_dir / "opt" / "readme.txt").exists())
        self.assertTrue((self.install_dir / "opt" / "link.txt").is_symlink())

    def test_real_extractor_rejects_escaping_symlink(self):
        deb = self.root / "evil.deb"
        deb.write_bytes(build_deb("1.11.24", escape=True))
        with self.assertRaises(tarfile.TarError):
            uf.install_deb(deb, self.install_dir, (1, 11, 22), uf.install_boosteroid.extract_deb)
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 22))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["boosteroid", "evil.deb"])


class RunEndToEnd(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.install_dir = self.root / "boosteroid"
        self.log = self.root / "bstr_client.log"
        self.log.write_text(LOG_BETA)
        fake_binary(self.install_dir / uf.BINARY_REL, "1.11.22")
        self.downloaded = []

    def tearDown(self):
        self._td.cleanup()

    def _download(self, url, dest):
        self.downloaded.append(url)
        Path(dest).write_bytes(b"deb")

    def _run(self, remote_xml=UPDATES_XML, deb_version="1.11.24", dry_run=False):
        def extract(deb_path, target_dir):
            fake_binary(Path(target_dir) / uf.BINARY_REL, deb_version)
        return uf.run(
            log_path=self.log, install_dir=self.install_dir, dry_run=dry_run,
            fetch=lambda url: remote_xml, download=self._download, extract=extract,
        )

    def test_stale_bundle_triggers_deb_install(self):
        self.assertEqual(self._run(), 0)
        self.assertEqual(self.downloaded, [uf.channel_urls(BETA_URL).deb])
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 24))
        self.assertEqual(uf.read_state(self.install_dir), "latest:1.11.24")

    def test_second_run_after_stale_deb_does_not_redownload(self):
        self._run(deb_version="1.11.22")
        self.assertEqual(len(self.downloaded), 1)
        self.assertEqual(uf.read_state(self.install_dir), "latest:1.11.24")
        self._run(deb_version="1.11.22")
        self.assertEqual(len(self.downloaded), 1, "must not download again for the same remote version")

    def test_up_to_date_is_noop(self):
        fake_binary(self.install_dir / uf.BINARY_REL, "1.11.24")
        self.assertEqual(self._run(), 0)
        self.assertEqual(self.downloaded, [])
        self.assertEqual(uf.read_state(self.install_dir), "")

    def test_dry_run_changes_nothing(self):
        self.assertEqual(self._run(dry_run=True), 0)
        self.assertEqual(self.downloaded, [])
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 22))
        self.assertEqual(uf.read_state(self.install_dir), "")

    def test_no_bundle_in_log_is_noop(self):
        self.log.write_text("no updates ever\n")
        self.assertEqual(self._run(), 0)
        self.assertEqual(self.downloaded, [])

    def test_corrupt_deb_is_logged_and_not_retried(self):
        def extract(deb_path, target_dir):
            raise tarfile.ReadError("not a tar")
        rc = uf.run(log_path=self.log, install_dir=self.install_dir, dry_run=False,
                    fetch=lambda url: UPDATES_XML, download=self._download, extract=extract)
        self.assertEqual(rc, 0)
        self.assertEqual(uf.binary_version(self.install_dir / uf.BINARY_REL), (1, 11, 22))
        self.assertEqual(uf.read_state(self.install_dir), "latest:1.11.24",
                         "a broken .deb must not be re-downloaded on every launch")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["boosteroid", "bstr_client.log"])

    def test_unwritable_state_does_not_raise(self):
        def extract(deb_path, target_dir):
            fake_binary(Path(target_dir) / uf.BINARY_REL, "1.11.22")  # stale, so no swap
        self.install_dir.chmod(0o555)
        try:
            rc = uf.run(log_path=self.log, install_dir=self.install_dir, dry_run=False,
                        fetch=lambda url: UPDATES_XML, download=self._download, extract=extract)
        finally:
            self.install_dir.chmod(0o755)
        self.assertEqual(rc, 0)

    def test_unreachable_updates_xml_is_noop(self):
        def fetch(url):
            raise OSError("offline")
        rc = uf.run(log_path=self.log, install_dir=self.install_dir, dry_run=False,
                    fetch=fetch, download=self._download, extract=None)
        self.assertEqual(rc, 0)
        self.assertEqual(self.downloaded, [])


if __name__ == "__main__":
    unittest.main()
