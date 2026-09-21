"""
Cross-Android-version regression tests for system/rish-install.sh.

`--skip-verification` / `--bypass-low-target-sdk-block` are Android 14+
`pm install` options; an unconditional flag build breaks the whole install
on any older `pm` that rejects unknown options. This is the only physical
verification available for that behavior (`pm install` itself was probed
manually on a single SDK 37 device), so these tests exercise the actual
shell script - not a Python re-implementation of its logic - against a stub
`rish` binary that impersonates several Android SDK levels.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RISH_SCRIPT = REPO_ROOT / "system" / "rish-install.sh"

# $2 is always the inner command: the script's rish() wrapper invokes
# `command rish -c "<cmd>"`.
STUB_RISH = """#!{bash}
echo "Entering shell..."
CMD="$2"
case "$CMD" in
    *"getprop ro.build.version.sdk"*) echo "$STUB_SDK" ;;
    *"am get-current-user"*)
        [ -n "$STUB_LOG" ] && echo "RISH_APPLICATION_ID=$RISH_APPLICATION_ID" >> "$STUB_LOG"
        echo 0 ;;
    *"pm list packages"*) : ;;
    *"pm install"*)
        echo "$CMD" >> "$STUB_LOG"
        if [ "$STUB_REJECT_FLAGS" = "1" ] && echo "$CMD" | grep -q -- "--"; then
            case "$CMD" in
                *--skip-verification*|*--bypass-low-target-sdk-block*)
                    echo "Error: Unknown option: --skip-verification"; exit 0 ;;
            esac
        fi
        if [ -n "$STUB_INSTALL_OUTPUT" ]; then echo "$STUB_INSTALL_OUTPUT"; exit 0; fi
        echo "Success" ;;
    *"-d '/data/local/tmp/enhancify'"*) echo "Exists" ;;
    *"[ -e "*) echo "Exists" ;;
    *) : ;;
esac
exit 0
"""


class RishScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.stub_bin = self.tmp / "bin"
        self.stub_bin.mkdir()
        rish_stub = self.stub_bin / "rish"
        rish_stub.write_text(STUB_RISH.format(bash=shutil.which("bash") or "/bin/bash"))
        rish_stub.chmod(rish_stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        self.storage = self.tmp / "storage"
        self.storage.mkdir()
        self.stub_log = self.tmp / "stub_calls.log"
        self.config_file = self.tmp / ".config"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, sdk, reject_flags=False, config_text=None, unset_env=None, install_output=None):
        if config_text is not None:
            self.config_file.write_text(config_text)

        env = dict(os.environ)
        env["PATH"] = f"{self.stub_bin}:{env.get('PATH', '')}"
        env["STUB_SDK"] = str(sdk)
        env["STUB_LOG"] = str(self.stub_log)
        env["STUB_REJECT_FLAGS"] = "1" if reject_flags else "0"
        env["ENHANCIFY_CONFIG_FILE"] = str(self.config_file)
        if install_output is not None:
            env["STUB_INSTALL_OUTPUT"] = install_output
        for key in unset_env or ():
            env.pop(key, None)

        return subprocess.run(
            ["bash", str(RISH_SCRIPT), "com.test.app", "TestApp", "TestApp-1.0-Src", str(self.storage)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _log_lines(self):
        return self.stub_log.read_text().splitlines() if self.stub_log.exists() else []

    def _install_lines(self):
        return [line for line in self._log_lines() if line.startswith("pm install")]

    def _rish_log(self):
        f = self.storage / "rish_log.txt"
        return f.read_text() if f.exists() else ""

    def test_modern_sdk_passes_both_flags(self):
        result = self._run(
            sdk=34,
            config_text="SKIP_VERIFICATION='on'\nBYPASS_LOW_TARGET_SDK_BLOCK='on'\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 1)
        self.assertIn("--skip-verification", install_lines[0])
        self.assertIn("--bypass-low-target-sdk-block", install_lines[0])

        self.assertEqual((self.storage / "install_type.txt").read_text().strip(), "new")
        self.assertIn("Install output: Success", self._rish_log())

    def test_legacy_sdk_drops_unsupported_flags(self):
        result = self._run(
            sdk=33,
            config_text="SKIP_VERIFICATION='on'\nBYPASS_LOW_TARGET_SDK_BLOCK='on'\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 1)
        self.assertNotIn("--skip-verification", install_lines[0])
        self.assertNotIn("--bypass-low-target-sdk-block", install_lines[0])
        self.assertIn(
            "Skipping --skip-verification (needs SDK 34+, device is 33)", self._rish_log()
        )

    def test_retries_without_flags_when_pm_rejects_them(self):
        result = self._run(
            sdk=36,
            reject_flags=True,
            config_text="SKIP_VERIFICATION='on'\nBYPASS_LOW_TARGET_SDK_BLOCK='on'\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 2)
        self.assertIn("--skip-verification", install_lines[0])
        self.assertNotIn("--skip-verification", install_lines[1])
        self.assertNotIn("--bypass-low-target-sdk-block", install_lines[1])
        self.assertIn("retrying without them", self._rish_log())

    def test_config_defaults_when_config_missing(self):
        result = self._run(sdk=35)  # config file never written
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 1)
        self.assertNotIn("--skip-verification", install_lines[0])
        self.assertNotIn("--bypass-low-target-sdk-block", install_lines[0])
        self.assertIn("Config file not found at:", self._rish_log())

    def test_rish_application_id_defaulted(self):
        result = self._run(sdk=35, unset_env=["RISH_APPLICATION_ID", "MANAGER_APPLICATION_ID"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RISH_APPLICATION_ID=com.termux", self._log_lines())

    def test_downgrade_flag_added_when_config_allows(self):
        result = self._run(
            sdk=34,
            config_text="ALLOW_APP_VERSION_DOWNGRADE='on'\n",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 1)
        self.assertIn(" -d ", install_lines[0])
        self.assertIn("Adding flag: -d", self._rish_log())

    def test_downgrade_flag_absent_by_default(self):
        result = self._run(sdk=34, config_text="SOURCE='Anddea'\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        install_lines = self._install_lines()
        self.assertEqual(len(install_lines), 1)
        self.assertNotIn(" -d ", install_lines[0])

    def test_downgrade_failure_writes_failure_code(self):
        result = self._run(
            sdk=34,
            install_output=(
                "Failure [INSTALL_FAILED_VERSION_DOWNGRADE: Downgrade detected: "
                "Update version code 312270001 is older than current 312271001]"
            ),
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

        self.assertEqual(
            (self.storage / "install_failure_code.txt").read_text().strip(),
            "INSTALL_FAILED_VERSION_DOWNGRADE",
        )
        self.assertIn("Downgrade detected", (self.storage / "install_error.txt").read_text())

    def test_success_clears_failure_code(self):
        (self.storage / "install_failure_code.txt").write_text("INSTALL_FAILED_VERSION_DOWNGRADE")
        result = self._run(sdk=34)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.storage / "install_failure_code.txt").exists())



if __name__ == "__main__":
    unittest.main()
