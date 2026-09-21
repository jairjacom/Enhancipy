"""
Install-mode branch routing regression tests (src/installer.py).

install_or_export() has three mutually exclusive paths: root mount, rish
install (with dex optimization), and non-privilege export via
`termux-open --view`. A wrong has_root/has_rish reading — e.g. a stale
cached privilege snapshot upstream — silently falls through to the
non-privilege export path, which pops the Android package installer and
never touches rish-install.sh or dex optimization. These tests pin which
branch actually executes for each privilege combination.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import ConfigManager
from src.installer import AppInstaller


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
            patch("src.installer.subprocess.run") as mock_subproc,
        ):
            mock_run_command.return_value = (0, "Install succeeded.", "")

            ok, msg = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=True,
            )

        self.assertTrue(ok)
        self.assertIn("Rish", msg)
        mock_run_command.assert_called_once()
        rish_cmd = mock_run_command.call_args[0][0]
        self.assertIn(str(self.workspace / "system" / "rish-install.sh"), rish_cmd)
        mock_dexopt.assert_called_once()
        # LAUNCH_APP_AFTER_MOUNT defaults on: a post-install `rish -c am start`
        # launch is expected, but it must never fall through to the
        # non-privilege termux-open export path.
        mock_subproc.assert_called_once()
        self.assertEqual(mock_subproc.call_args[0][0][0], "rish")

    def test_non_privilege_mode_exports_and_never_touches_rish(self):
        with (
            patch("src.installer.run_command") as mock_run_command,
            patch("src.installer.shutil.which", return_value=None),
        ):
            ok, msg = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=False, has_rish=False,
            )

        self.assertTrue(ok)
        self.assertIn("exported to", msg)
        mock_run_command.assert_not_called()
        exported = self.workspace / "storage" / "Patched" / "TestApp-1.0-TestSrc.apk"
        self.assertTrue(exported.exists())

    def test_root_mode_mounts_via_su_and_skips_rish(self):
        with patch("src.installer.run_command") as mock_run_command:
            mock_run_command.return_value = (0, "mounted", "")

            ok, msg = self.installer.install_or_export(
                self.apk_path, "TestApp", "com.test.app", "1.0", "TestSrc",
                has_root=True, has_rish=True,
            )

        self.assertTrue(ok)
        self.assertIn("Root", msg)
        mock_run_command.assert_called_once()
        mount_cmd = mock_run_command.call_args[0][0]
        self.assertEqual(mount_cmd[0], "su")


if __name__ == "__main__":
    unittest.main()
