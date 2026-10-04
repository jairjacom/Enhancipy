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


if __name__ == "__main__":
    unittest.main()
