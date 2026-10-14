"""
Behavior tests for keystore signing wiring (patcher, installer, KeystoreManager).

Rule under test: with `Use_CUSTOM_KEYSTORE` off the CLI signs with the stable
<storage>/revancify.keystore (pinning the alias already stored in it, since each
CLI family creates the file with its own default alias); with it on, the CLI
never touches that file and the installer signs with the key keystore.json names.

Keystore fixtures are real: generated with keytool and the vendored Bouncy Castle
jar, because the contract is that the BKS header parser agrees with real files.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from src.config import config
from src.features import KeystoreManager
from src.patcher import PatchExecutionConfig, PatcherEngine, read_bks_first_alias

REPO = Path(__file__).resolve().parent.parent
BC_JAR = next((REPO / "utils").glob("bcprov*.jar"))
HAS_KEYTOOL = shutil.which("keytool") is not None
NEED_KEYTOOL = unittest.skipUnless(HAS_KEYTOOL, "keytool required")

PASSWORD = "secret123"


def _keytool(path: Path, store_type: str, alias: str) -> None:
    cmd = [
        "keytool", "-genkeypair", "-keystore", str(path), "-storetype", store_type,
        "-alias", alias, "-keyalg", "RSA", "-keysize", "2048", "-validity", "1",
        "-storepass", PASSWORD, "-keypass", PASSWORD, "-dname", "CN=test",
    ]
    if store_type == "BKS":
        cmd += [
            "-providerclass", "org.bouncycastle.jce.provider.BouncyCastleProvider",
            "-providerpath", str(BC_JAR),
        ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


def _set_toggle(value: str) -> None:
    config.set("Use_CUSTOM_KEYSTORE", value)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.addCleanup(_set_toggle, "off")
        patcher = mock.patch.object(config, "cli_detection_file", self.tmp / "cli_detection.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.engine = PatcherEngine(workspace_dir=self.tmp)
        self.engine.storage_dir.mkdir(parents=True, exist_ok=True)


@NEED_KEYTOOL
class TestReadBksFirstAlias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        cls.bks = cls.dir / "k.bks"
        cls.p12 = cls.dir / "k.p12"
        _keytool(cls.bks, "BKS", "ReVanced Key")
        _keytool(cls.p12, "PKCS12", "other")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_reads_alias_from_real_bks(self):
        self.assertEqual(read_bks_first_alias(self.bks), "ReVanced Key")

    def test_rejects_non_bks_empty_and_truncated(self):
        empty = self.dir / "empty"
        empty.write_bytes(b"")
        truncated = self.dir / "trunc"
        truncated.write_bytes(self.bks.read_bytes()[:10])
        self.assertIsNone(read_bks_first_alias(self.p12))
        self.assertIsNone(read_bks_first_alias(empty))
        self.assertIsNone(read_bks_first_alias(truncated))
        self.assertIsNone(read_bks_first_alias(self.dir / "does-not-exist"))


class TestSigningArgs(_Base):
    def test_off_without_file_passes_only_keystore_path(self):
        _set_toggle("off")
        args, tmp = self.engine._signing_args({"unsigned": True})
        self.assertEqual(args, [f"--keystore={self.engine.storage_dir / 'revancify.keystore'}"])
        self.assertIsNone(tmp)

    def test_off_ignores_unsigned_capability(self):
        _set_toggle("off")
        args, _ = self.engine._signing_args({"unsigned": True})
        self.assertNotIn("--unsigned", args)

    def test_off_with_unparseable_file_passes_no_alias(self):
        _set_toggle("off")
        (self.engine.storage_dir / "revancify.keystore").write_bytes(b"not a keystore")
        args, _ = self.engine._signing_args({})
        self.assertEqual(len(args), 1)

    @NEED_KEYTOOL
    def test_off_pins_alias_stored_in_existing_keystore(self):
        _set_toggle("off")
        ks = self.engine.storage_dir / "revancify.keystore"
        _keytool(ks, "BKS", "ReVanced Key")
        args, tmp = self.engine._signing_args({})
        self.assertEqual(args, [f"--keystore={ks}", "--keystore-entry-alias=ReVanced Key"])
        self.assertIsNone(tmp)

    def test_on_with_unsigned_cli_emits_unsigned(self):
        _set_toggle("on")
        self.assertEqual(self.engine._signing_args({"unsigned": True}), (["--unsigned"], None))

    def test_on_without_unsigned_uses_throwaway_key_not_revancify_keystore(self):
        _set_toggle("on")
        args, tmp = self.engine._signing_args({"unsigned": False})
        try:
            self.assertIsNotNone(tmp)
            self.assertTrue(tmp.is_dir())
            self.assertEqual(len(args), 1)
            ks_path = Path(args[0].removeprefix("--keystore="))
            self.assertNotEqual(ks_path.name, "revancify.keystore")
            self.assertEqual(ks_path.parent, tmp)
            self.assertFalse(ks_path.exists())
        finally:
            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)


class TestRunPatch(_Base):
    def _cfg(self, cli_name: str = "CLI-b.jar") -> PatchExecutionConfig:
        return PatchExecutionConfig(
            source_name="Src", app_name="App", app_version="1.0", pkg_name="p.k.g",
            input_apk_path=self.tmp / "in.apk", output_apk_path=self.tmp / "out.apk",
            cli_jar=self.tmp / cli_name, patches_file=self.tmp / "p.mpp",
            enabled_patches=set(), patch_options=[],
        )

    def _run(self, cfg, probe_result=None):
        """Run run_patch with no JVM; returns (result, popen_cmds, probe_mock)."""
        cmds = []

        class _Proc:
            stdout = iter(())
            returncode = 1

            def wait(self):
                return 1

        real_popen = subprocess.Popen

        def fake_popen(cmd, *a, **kw):
            if isinstance(cmd, list) and cmd and cmd[0] == "java":
                cmds.append(cmd)
                return _Proc()
            return real_popen(cmd, *a, **kw)

        probe = mock.Mock(return_value=probe_result or {})
        with mock.patch("src.patcher.shutil.which", return_value="/usr/bin/java"), \
             mock.patch("src.patcher.env.detect_java_version", return_value=("21", "")), \
             mock.patch("src.patcher.env.get_memory_info", return_value=(4096, 4096, "4 GB")), \
             mock.patch("src.patcher.assets_mgr.get_patches_extension", return_value=".mpp"), \
             mock.patch("src.patcher.assets_mgr.resolve_cli_repo", return_value="x/y"), \
             mock.patch("src.patcher.assets_mgr.detect_cli_capabilities", probe), \
             mock.patch("src.patcher.subprocess.Popen", side_effect=fake_popen):
            result = self.engine.run_patch(cfg)
        return result, cmds, probe

    def test_custom_keystore_on_without_keystore_blocks_before_launching_cli(self):
        _set_toggle("on")
        (self.tmp / "keystore").mkdir(exist_ok=True)
        (result, cmds, _) = self._run(self._cfg())
        ok, msg = result
        self.assertFalse(ok)
        self.assertIn("No custom keystore is set up", msg)
        self.assertEqual(cmds, [])

    def test_stale_capability_cache_is_reprobed_for_the_actual_jar(self):
        _set_toggle("off")
        config.cli_detection_file.write_text(json.dumps(
            {"cli_jar": "CLI-a.jar", "unsigned": True, "riplib": False, "striplibs": False}
        ))
        fresh = {"cli_jar": "CLI-b.jar", "unsigned": False, "riplib": False, "striplibs": False}
        _, cmds, probe = self._run(self._cfg("CLI-b.jar"), probe_result=fresh)
        probe.assert_called_once_with(self.tmp / "CLI-b.jar")
        self.assertEqual(len(cmds), 1)

    def test_matching_capability_cache_is_not_reprobed(self):
        _set_toggle("off")
        config.cli_detection_file.write_text(json.dumps(
            {"cli_jar": "CLI-b.jar", "unsigned": False, "riplib": False, "striplibs": False}
        ))
        _, cmds, probe = self._run(self._cfg("CLI-b.jar"))
        probe.assert_not_called()
        self.assertEqual(len(cmds), 1)

    def test_on_signing_temp_dir_is_removed_after_run(self):
        _set_toggle("on")
        ks = KeystoreManager(self.tmp)
        (ks.keystore_dir / "a.p12").write_bytes(b"x")
        ks.keystore_json.write_text(json.dumps({"a.p12": {
            "alias": "a", "keystore_password": "pw", "keystore_type": "PKCS12"}}))
        caps = {"cli_jar": "CLI-b.jar", "unsigned": False, "riplib": False, "striplibs": False}
        config.cli_detection_file.write_text(json.dumps(caps))
        _, cmds, _ = self._run(self._cfg("CLI-b.jar"))
        (arg,) = [a for a in cmds[0] if a.startswith("--keystore=")]
        self.assertFalse(Path(arg.removeprefix("--keystore=")).parent.exists())


class TestResolveActiveKeystore(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mgr = KeystoreManager(Path(self._tmp.name))

    def _write(self, meta):
        self.mgr.keystore_json.write_text(json.dumps(meta))

    def test_picks_the_file_named_in_json_not_an_unlisted_sibling(self):
        (self.mgr.keystore_dir / "aaa_unlisted.p12").write_bytes(b"x")
        (self.mgr.keystore_dir / "mine.jks").write_bytes(b"x")
        self._write({"mine.jks": {
            "alias": "al", "keystore_password": "pw", "private_key_password": "kp",
            "keystore_type": "jks"}})
        active, reason = self.mgr.resolve_active_keystore()
        self.assertEqual(reason, "")
        self.assertEqual(active.path.name, "mine.jks")
        self.assertEqual((active.alias, active.keystore_password, active.key_password), ("al", "pw", "kp"))
        self.assertEqual(active.keystore_type, "JKS")

    def test_missing_type_falls_back_to_extension_and_key_password_to_store_password(self):
        (self.mgr.keystore_dir / "k.bks").write_bytes(b"x")
        self._write({"k.bks": {"alias": "al", "keystore_password": "pw"}})
        active, _ = self.mgr.resolve_active_keystore()
        self.assertEqual(active.keystore_type, "BKS")
        self.assertEqual(active.key_password, "pw")

    def test_unusable_configurations_return_a_reason(self):
        active, reason = self.mgr.resolve_active_keystore()
        self.assertIsNone(active)
        self.assertIn("No custom keystore is set up", reason)

        self._write({"gone.p12": {"alias": "a", "keystore_password": "p"}})
        active, reason = self.mgr.resolve_active_keystore()
        self.assertIsNone(active)
        self.assertIn("'gone.p12' is missing", reason)

        (self.mgr.keystore_dir / "k.p12").write_bytes(b"x")
        self._write({"k.p12": {"alias": "", "keystore_password": "p"}})
        active, reason = self.mgr.resolve_active_keystore()
        self.assertIsNone(active)
        self.assertIn("alias or password missing", reason)

        self.mgr.keystore_json.write_text("{not json")
        active, reason = self.mgr.resolve_active_keystore()
        self.assertIsNone(active)
        self.assertIn("unreadable", reason)


@NEED_KEYTOOL
class TestImportRecordsRealType(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.dir = Path(cls._tmp.name)
        _keytool(cls.dir / "k.bks", "BKS", "a")
        _keytool(cls.dir / "p12_as.keystore", "PKCS12", "a")
        shutil.copy(cls.dir / "k.bks", cls.dir / "bks_as.keystore")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._ws = TemporaryDirectory()
        self.addCleanup(self._ws.cleanup)
        ws = Path(self._ws.name)
        (ws / "utils").mkdir()
        shutil.copy(BC_JAR, ws / "utils" / BC_JAR.name)
        self.mgr = KeystoreManager(ws)

    def _type(self):
        return next(iter(json.loads(self.mgr.keystore_json.read_text()).values()))["keystore_type"]

    def test_bks_extension_records_bks(self):
        ok, _ = self.mgr.import_keystore_file(self.dir / "k.bks", "a", PASSWORD, PASSWORD)
        self.assertTrue(ok)
        self.assertEqual(self._type(), "BKS")
        active, _ = self.mgr.resolve_active_keystore()
        self.assertEqual(active.keystore_type, "BKS")

    def test_dot_keystore_pkcs12_is_detected(self):
        ok, _ = self.mgr.import_keystore_file(self.dir / "p12_as.keystore", "a", PASSWORD, PASSWORD)
        self.assertTrue(ok)
        self.assertEqual(self._type(), "PKCS12")

    def test_dot_keystore_bks_is_detected_via_bouncy_castle(self):
        ok, _ = self.mgr.import_keystore_file(self.dir / "bks_as.keystore", "a", PASSWORD, PASSWORD)
        self.assertTrue(ok)
        self.assertEqual(self._type(), "BKS")

    def test_wrong_password_is_rejected_and_configures_nothing(self):
        ok, msg = self.mgr.import_keystore_file(self.dir / "p12_as.keystore", "a", "wrong-pass", "wrong-pass")
        self.assertFalse(ok)
        self.assertIn("wrong password or unsupported format", msg)
        self.assertFalse(self.mgr.keystore_json.exists())

    def test_rejected_import_keeps_the_existing_keystore(self):
        self.mgr.import_keystore_file(self.dir / "k.bks", "a", PASSWORD, PASSWORD)
        ok, _ = self.mgr.import_keystore_file(self.dir / "p12_as.keystore", "a", "wrong-pass", "wrong-pass")
        self.assertFalse(ok)
        active, _ = self.mgr.resolve_active_keystore()
        self.assertEqual(active.path.name, "k.bks")


if __name__ == "__main__":
    unittest.main()
