"""
Regression test for AntiSplitManager._sign_for_patching (src/antisplit.py).

Root cause this pins: APKEditor's bundle merge (antisplit_apkm/apks/xapk) and
optimize_native_libs's repackage step both destroy an APK's original v1/v2/v3
signing material -- the merge can't carry a per-split signature over to
merged content, and the native-lib repackage explicitly deletes
META-INF/*.SF/.RSA/.DSA/.EC and rewrites the zip from scratch (which also
drops the APK Signing Block implicitly). Cert-dependent patches (the Spoof
Signature patch family some sources use for paywall/license-check bypasses)
call into the patcher's own certificate-extraction code on the *input* APK
independent of any --keystore/--unsigned output flag, and crash with
NoCertificateException when there's nothing to extract -- surfacing as a
generic "Asset load failed"-style exception from the CLI, for any
bundle-distributed or multi-ABI app, regardless of patch source.

Reproduced and fixed against a real captured patch_log.txt (Niagara
Launcher via APKMirror bundle, source hoo-dles, "Enable Niagara Pro"
patch): re-running the exact failing CLI invocation against the
merged-then-stripped input reproduced
`app.morphe.util.NoCertificateException: Unable to extract certificate
from apk`; re-running it against the same input after
`_sign_for_patching` reported `INFO: Applied: Enable Niagara Pro` with no
exception.
"""

from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.antisplit import AntiSplitManager


def _make_fake_apk(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AndroidManifest.xml", b"fake-binary-xml")
        zf.writestr("classes.dex", b"fake-dex")


class TestSignForPatching(unittest.TestCase):
    """Uses the real vendored utils/apksigner.jar + keytool (both always
    present -- apksigner.jar is committed, keytool ships with every JDK),
    not mocks: the contract being pinned is that signing actually produces
    an extractable certificate, which a mocked subprocess can't prove."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)
        # Real workspace (for utils/apksigner.jar), isolated storage_dir
        # (so the throwaway keystore never touches real user storage).
        self.mgr = AntiSplitManager()
        self.mgr.storage_dir = tmp_path / "storage"
        self.mgr.merge_keystore = self.mgr.storage_dir / "antisplit.keystore"
        self.apk_path = tmp_path / "fake.apk"
        _make_fake_apk(self.apk_path)

    def test_sign_adds_extractable_certificate(self):
        self.assertFalse(
            b"APK Sig Block 42" in self.apk_path.read_bytes(),
            "fixture must start with no signing material",
        )

        ok = self.mgr._sign_for_patching(self.apk_path)

        self.assertTrue(ok)
        signed_bytes = self.apk_path.read_bytes()
        self.assertIn(b"APK Sig Block 42", signed_bytes)
        with zipfile.ZipFile(self.apk_path) as zf:
            names = zf.namelist()
        self.assertTrue(any(n.endswith(".RSA") or n.endswith(".EC") for n in names))
        self.assertIn("META-INF/MANIFEST.MF", names)

    def test_keystore_generated_once_and_reused(self):
        self.assertFalse(self.mgr.merge_keystore.exists())
        self.assertTrue(self.mgr._ensure_signing_keystore())
        self.assertTrue(self.mgr.merge_keystore.exists())
        first_mtime = self.mgr.merge_keystore.stat().st_mtime_ns

        self.assertTrue(self.mgr._ensure_signing_keystore())
        self.assertEqual(self.mgr.merge_keystore.stat().st_mtime_ns, first_mtime)


class TestMergeForcesExtractNativeLibsFalse(unittest.TestCase):
    """Root cause: APKEditor's default `-extractNativeLibs manifest` merge
    mode is supposed to auto-detect and apply the source app's own
    extractNativeLibs value, but was observed (via a real captured
    patch_log.txt + rish_log.txt for Niagara Launcher) producing a merged
    APK with android:extractNativeLibs=false in the manifest while its
    native libs were still DEFLATE-compressed -- an invalid combination
    that Android's installer rejects with `INSTALL_FAILED_INVALID_APK:
    Failed to extract native libraries, res=-2`. Forcing
    `-extractNativeLibs false` explicitly removes the ambiguity: APKEditor
    then always stores libraries uncompressed + 4096-aligned to match,
    which is valid regardless of what the source manifest originally
    declared (uncompressed is also valid when extractNativeLibs=true).
    These tests pin that the flag is actually passed to APKEditor, not
    APKEditor's own internal behavior (that's a vendored third-party jar,
    out of scope to re-prove here)."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.mgr = AntiSplitManager()
        self.captured_cmds = []

        def fake_run_command(cmd, timeout=None):
            self.captured_cmds.append(cmd)
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            return 0, "", ""

        patcher = mock.patch("src.antisplit.run_command", side_effect=fake_run_command)
        patcher.start()
        self.addCleanup(patcher.stop)
        mock.patch.object(self.mgr, "ensure_apkeditor", return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.mgr, "_sign_for_patching", return_value=True).start()

    def _assert_flag_present(self):
        self.assertEqual(len(self.captured_cmds), 1)
        cmd = self.captured_cmds[0]
        self.assertIn("-extractNativeLibs", cmd)
        self.assertEqual(cmd[cmd.index("-extractNativeLibs") + 1], "false")

    def test_antisplit_apkm_forces_flag(self):
        apkm = self.tmp_path / "bundle.apkm"
        with zipfile.ZipFile(apkm, "w") as zf:
            zf.writestr("base.apk", b"dummy")
        ok = self.mgr.antisplit_apkm(apkm, self.tmp_path / "out.apk")
        self.assertTrue(ok)
        self._assert_flag_present()

    def test_antisplit_apks_forces_flag(self):
        apks = self.tmp_path / "bundle.apks"
        with zipfile.ZipFile(apks, "w") as zf:
            zf.writestr("base.apk", b"dummy")
        ok = self.mgr.antisplit_apks(apks, self.tmp_path / "out.apk")
        self.assertTrue(ok)
        self._assert_flag_present()

    def test_antisplit_xapk_forces_flag(self):
        xapk = self.tmp_path / "bundle.xapk"
        with zipfile.ZipFile(xapk, "w") as zf:
            zf.writestr("manifest.json", b'{"split_apks": [{"id": "base", "file": "base.apk"}]}')
            zf.writestr("base.apk", b"dummy")
        ok = self.mgr.antisplit_xapk(xapk, self.tmp_path / "out.apk")
        self.assertTrue(ok)
        self._assert_flag_present()


class TestOptimizeNativeLibsStoresUncompressed(unittest.TestCase):
    """Root cause: optimize_native_libs's repackage step force-compressed
    every file except .arsc -- including native libs -- with no regard for
    the app's android:extractNativeLibs manifest value. A compressed .so
    with extractNativeLibs=false fails to install the exact same way as
    the bundle-merge case above (same `res=-2` error), and this is the
    DEFAULT path (OPTIMIZE_LIBS defaults "on" for any multi-ABI app, not
    just bundles). Native libs must be stored uncompressed, matching
    .arsc -- valid regardless of the manifest's actual declared value."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_path = Path(self._tmp.name)
        self.mgr = AntiSplitManager()
        self.mgr.storage_dir = tmp_path / "storage"
        self.mgr.merge_keystore = self.mgr.storage_dir / "antisplit.keystore"

        self.apk_path = tmp_path / "app.apk"
        with zipfile.ZipFile(self.apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("AndroidManifest.xml", b"fake-binary-xml")
            zf.writestr("lib/arm64-v8a/libfoo.so", b"\x7fELF" + b"\x00" * 200)
            zf.writestr("lib/armeabi-v7a/libfoo.so", b"\x7fELF" + b"\x00" * 200)
            zf.writestr("resources.arsc", b"\x00" * 50)

        badge_output = "native-code: 'arm64-v8a' 'armeabi-v7a'\n"
        patcher = mock.patch(
            "src.antisplit.run_command",
            return_value=(0, badge_output, ""),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        mock.patch.object(self.mgr, "ensure_aapt2", return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(self.mgr, "_sign_for_patching", return_value=True).start()
        mock.patch("src.antisplit.env.get_arch", return_value="arm64-v8a").start()

    def test_native_libs_stored_uncompressed(self):
        ok = self.mgr.optimize_native_libs(self.apk_path)
        self.assertTrue(ok)
        with zipfile.ZipFile(self.apk_path) as zf:
            libs = [i for i in zf.infolist() if i.filename.endswith(".so")]
            self.assertTrue(libs, "expected at least one lib entry to remain")
            for info in libs:
                self.assertEqual(
                    info.compress_type,
                    zipfile.ZIP_STORED,
                    f"{info.filename} must be stored uncompressed",
                )


if __name__ == "__main__":
    unittest.main()
