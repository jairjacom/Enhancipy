"""
Install-mode branch routing regression tests (src/installer.py).

install_or_export() has three mutually exclusive paths: root mount, rish
install (with dex optimization), and non-privilege export via
`termux-open --view`. A wrong has_root/has_rish reading — e.g. a stale
cached privilege snapshot upstream — silently falls through to the
non-privilege export path, which pops the Android package installer and
never touches rish-install.sh or dex optimization. These tests pin which
branch actually executes for each privilege combination.

run_dex_optimization() and the rish branch's post-install steps also get
their own coverage here: `rish` always exits 0 regardless of the inner
command's outcome, so a real failure (invalid filter, missing package, a
filter that never applied) is text-only and must not be reported as
success.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import ConfigManager
from src.installer import AppInstaller, CONFLICT_VERSION_DOWNGRADE


class TestInstallModeRouting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        (self.workspace / "system").mkdir(parents=True, exist_ok=True)
        (self.workspace / "system" / "rish-install.sh").write_text("#!/bin/sh\nexit 0\n")
        (self.workspace / "system" / "mount.sh").write_text("#!/bin/sh\nexit 0\n")

        self.apk_path = self.workspace / "patched.apk"
        self.apk_path.write_bytes(b"fake-apk")

        self.installer = AppInstaller(workspace_dir=self.workspace)
        self.config_patch = patch("src.installer.config", ConfigManager(self.workspace))
        self.config_patch.start()

    def tearDown(self):
        self.config_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rish_mode_invokes_rish_script_and_dex_optimization(self):
        with (
            patch("src.installer.run_command") as mock_run_command,
            patch.object(self.installer, "run_dex_optimization") as mock_dexopt,
            patch("src.installer.run_rish") as mock_run_rish,
            patch.dict("os.environ", {}, clear=False),
        ):
            import os as _os

            _os.environ.pop("RISH_APPLICATION_ID", None)
            mock_run_command.return_value = (0, "Install succeeded.", "")
            mock_dexopt.return_value = (True, "DEX optimized (quicken)")

            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertTrue(res.ok)
        self.assertIn("Rish", res.message)
        mock_run_command.assert_called_once()
        rish_cmd = mock_run_command.call_args[0][0]
        self.assertIn(str(self.workspace / "system" / "rish-install.sh"), rish_cmd)
        mock_dexopt.assert_called_once()

        call_kwargs = mock_run_command.call_args.kwargs
        self.assertIn("ENHANCIFY_CONFIG_FILE", call_kwargs["env"])
        self.assertIn("RISH_APPLICATION_ID", call_kwargs["env"])
        self.assertGreaterEqual(call_kwargs["timeout"], 300)

        # LAUNCH_APP_AFTER_MOUNT defaults on: a post-install launch via the
        # rish gateway is expected, but it must never fall through to the
        # non-privilege termux-open export path.
        mock_run_rish.assert_called_once()

    def test_rish_mode_reports_dex_failure_without_failing_the_install(self):
        with (
            patch("src.installer.run_command") as mock_run_command,
            patch.object(self.installer, "run_dex_optimization") as mock_dexopt,
            patch("src.installer.run_rish"),
        ):
            mock_run_command.return_value = (0, "Install succeeded.", "")
            mock_dexopt.return_value = (False, "Package not found: com.test.app")

            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertTrue(res.ok)
        self.assertIn("DEX optimization failed", res.message)
        self.assertIn("Package not found", res.message)

    def test_rish_mode_clears_stale_result_files(self):
        storage = self.workspace / "storage"
        storage.mkdir(parents=True, exist_ok=True)
        (storage / "install_type.txt").write_text("update")
        (storage / "rish_log.txt").write_text("stale log")
        (storage / "install_error.txt").write_text("stale error")

        with patch("src.installer.run_command", return_value=(1, "", "")):
            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertFalse(res.ok)
        self.assertIn("no output", res.message)
        self.assertFalse((storage / "install_type.txt").exists())
        self.assertFalse((storage / "rish_log.txt").exists())
        self.assertFalse((storage / "install_error.txt").exists())

    def test_non_privilege_mode_exports_and_never_touches_rish(self):
        with (
            patch("src.installer.run_command") as mock_run_command,
            patch("src.installer.shutil.which", return_value=None),
        ):
            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=False,
            )

        self.assertTrue(res.ok)
        self.assertIn("exported to", res.message)
        mock_run_command.assert_not_called()
        exported = self.workspace / "storage" / "Patched" / "TestApp-1.0-TestSrc.apk"
        self.assertTrue(exported.exists())

    def test_root_mode_mounts_via_su_and_skips_rish(self):
        with patch("src.installer.run_command") as mock_run_command:
            mock_run_command.return_value = (0, "Mounted.", "")

            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=True, has_rish=True,
            )

        self.assertTrue(res.ok)
        self.assertIn("Root", res.message)
        mount_cmd = mock_run_command.call_args[0][0]
        self.assertEqual(mount_cmd[0], "su")

    def test_rish_downgrade_failure_surfaces_conflict(self):
        storage = self.workspace / "storage"
        storage.mkdir(parents=True, exist_ok=True)

        def fake_run_command(cmd, **kwargs):
            (storage / "install_error.txt").write_text(
                "INSTALL_FAILED_VERSION_DOWNGRADE: Downgrade detected: Update "
                "version code 312270001 is older than current 312271001"
            )
            (storage / "install_failure_code.txt").write_text("INSTALL_FAILED_VERSION_DOWNGRADE")
            return (1, "", "")

        with patch("src.installer.run_command", side_effect=fake_run_command):
            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertFalse(res.ok)
        self.assertEqual(res.conflict, CONFLICT_VERSION_DOWNGRADE)
        self.assertEqual(res.exported_name, "TestApp-1.0-TestSrc")
        self.assertIn("312270001", res.message)
        self.assertIn("312271001", res.message)

    def test_non_downgrade_failure_has_no_conflict(self):
        storage = self.workspace / "storage"
        storage.mkdir(parents=True, exist_ok=True)

        def fake_run_command(cmd, **kwargs):
            (storage / "install_error.txt").write_text("Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]")
            (storage / "install_failure_code.txt").write_text("INSTALL_FAILED_UPDATE_INCOMPATIBLE")
            return (1, "", "")

        with patch("src.installer.run_command", side_effect=fake_run_command):
            res = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertFalse(res.ok)
        self.assertIsNone(res.conflict)

    def test_uninstall_and_reinstall_runs_uninstall_then_script(self):
        with (
            patch("src.installer.run_rish", return_value=(0, "Success", "")) as mock_run_rish,
            patch("src.installer.run_command", return_value=(0, "", "")) as mock_run_command,
            patch.object(self.installer, "run_dex_optimization", return_value=(True, "DEX optimized (speed)")),
        ):
            res = self.installer.uninstall_and_reinstall(
                "TestApp", "com.test.app", "TestApp-1.0-TestSrc",
            )

        self.assertTrue(res.ok)
        first_call = mock_run_rish.call_args_list[0]
        self.assertEqual(first_call[0][0], "pm uninstall --user current com.test.app")
        mock_run_command.assert_called_once()
        script_cmd = mock_run_command.call_args[0][0]
        self.assertIn(str(self.workspace / "system" / "rish-install.sh"), script_cmd)

    def test_uninstall_failure_is_reported_without_reinstalling(self):
        with (
            patch(
                "src.installer.run_rish",
                return_value=(0, "", "Failure [DELETE_FAILED_INTERNAL_ERROR]"),
            ),
            patch("src.installer.run_command") as mock_run_command,
        ):
            res = self.installer.uninstall_and_reinstall(
                "TestApp", "com.test.app", "TestApp-1.0-TestSrc",
            )

        self.assertFalse(res.ok)
        self.assertIn("Uninstall failed", res.message)
        mock_run_command.assert_not_called()


class TestDexOptimization(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.installer = AppInstaller(workspace_dir=self.workspace)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dex_optimization_fails_on_rc0_error_text(self):
        """rish exits 0 even when the inner command failed - a returncode
        check alone can never observe this."""
        with patch(
            "src.installer.run_rish",
            return_value=(0, "", "Error: Package not found: com.test.app"),
        ):
            ok, msg = self.installer.run_dex_optimization("com.test.app")

        self.assertFalse(ok)
        self.assertIn("Package not found", msg)

    def test_dex_optimization_requires_applied_status(self):
        def fake_run_rish(cmd, timeout=60):
            if cmd.startswith("cmd package compile"):
                return 0, "", ""
            return 0, "arm64: [status=verify] [reason=vdex]", ""

        with patch("src.installer.run_rish", side_effect=fake_run_rish):
            ok, msg = self.installer.run_dex_optimization("com.test.app", install_type="update")

        self.assertFalse(ok)

        def fake_run_rish_ok(cmd, timeout=60):
            if cmd.startswith("cmd package compile"):
                return 0, "", ""
            return 0, "arm64: [status=speed] [reason=cmdline]", ""

        with patch("src.installer.run_rish", side_effect=fake_run_rish_ok):
            ok, msg = self.installer.run_dex_optimization("com.test.app", install_type="update")

        self.assertTrue(ok)

    def test_dex_optimization_falls_back_when_filter_invalid(self):
        calls = []

        def fake_run_rish(cmd, timeout=60):
            calls.append(cmd)
            if cmd.startswith("cmd package compile"):
                if "quicken" in cmd:
                    return 0, "Error: Invalid compiler filter 'quicken'", ""
                return 0, "", ""
            return 0, "arm64: [status=speed] [reason=cmdline]", ""

        with patch("src.installer.run_rish", side_effect=fake_run_rish):
            ok, msg = self.installer.run_dex_optimization("com.test.app", install_type="new")

        self.assertTrue(ok)
        compile_calls = [c for c in calls if c.startswith("cmd package compile")]
        self.assertEqual(len(compile_calls), 2)
        self.assertIn("-m speed", compile_calls[1])

    def test_dex_optimization_accepts_unknown_dumpsys_format(self):
        def fake_run_rish(cmd, timeout=60):
            if cmd.startswith("cmd package compile"):
                return 0, "", ""
            return 0, "Dexopt state: (nothing parseable)", ""

        with patch("src.installer.run_rish", side_effect=fake_run_rish):
            ok, msg = self.installer.run_dex_optimization("com.test.app", install_type="update")

        self.assertTrue(ok)
        self.assertIn("status unverified", msg)


if __name__ == "__main__":
    unittest.main()
