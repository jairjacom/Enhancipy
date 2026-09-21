"""
Privilege-detection regression tests (src/environment.py).

check_privileges() memoizes its result for the lifetime of the Environment
instance. That is fine for cheap header re-renders but is wrong for the
actual install decision: rish/Shizuku can attach *after* the very first
(possibly too-early) probe, and a stale negative must not be trusted at
install time. refresh=True exists to bypass the cache; this pins that
contract so it can't silently regress back to "always cached".

Rish detection itself is covered here through src.utils.rish_available /
run_rish / rish_environ / strip_rish_banner: `rish` always exits 0 regardless
of the inner command's outcome and silently no-ops (rc 0, empty output) when
RISH_APPLICATION_ID is unset, so returncode-based detection is a false
positive/negative trap. These tests pin the marker-based replacement and the
timeout budget that caused a real outage (a 1s probe timeout against a
measured ~1.0s rish round trip).
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from src.environment import Environment
from src.utils import rish_environ, strip_rish_banner


def _completed(returncode: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


class TestRishDetectionHelpers(unittest.TestCase):
    def test_strip_rish_banner_removes_banner_and_crs(self):
        self.assertEqual(strip_rish_banner("Entering shell...\r\nout\r\n"), "out\n")

    def test_rish_environ_fills_missing_application_id(self):
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("RISH_APPLICATION_ID", None)
            overlay = rish_environ()
        self.assertEqual(overlay["RISH_APPLICATION_ID"], "com.termux")

    def test_rish_environ_respects_existing_application_id(self):
        with patch.dict("os.environ", {"RISH_APPLICATION_ID": "com.foo"}):
            overlay = rish_environ()
        self.assertNotIn("RISH_APPLICATION_ID", overlay)


class TestPrivilegeCaching(unittest.TestCase):
    def setUp(self):
        self.env = Environment(workspace_dir=None)

    def test_probe_rejects_rc0_with_no_marker(self):
        """rish exits 0 unconditionally; an rc-0/empty-output response is the
        silent-no-op signature (e.g. RISH_APPLICATION_ID unset / Shizuku not
        authorized), not a working rish - it must not read as Rish Mode."""
        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.utils.run_command", return_value=(0, "Entering shell...\n", "")),
        ):
            result = self.env.check_privileges()
        self.assertEqual(result, (False, False, "Non-privilege Mode"))

    def test_probe_accepts_marker_with_banner_noise(self):
        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch(
                "src.utils.run_command",
                return_value=(0, "Entering shell...\r\nENH_RISH_OK\r\n", ""),
            ),
        ):
            result = self.env.check_privileges()
        self.assertEqual(result, (False, True, "Rish Mode"))

    def test_probe_treats_timeout_as_unavailable_and_budgets_over_five_seconds(self):
        seen_kwargs = {}

        def fake_run_command(cmd, **kwargs):
            seen_kwargs.update(kwargs)
            return 124, "", "Command timed out"

        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.utils.run_command", side_effect=fake_run_command),
        ):
            result = self.env.check_privileges()

        self.assertEqual(result, (False, False, "Non-privilege Mode"))
        self.assertGreaterEqual(seen_kwargs.get("timeout", 0), 5)

    def test_plain_call_returns_cached_result_even_when_state_changed(self):
        """First probe finds nothing; rish becomes available later; an
        uncached-unaware caller must still see the original snapshot."""
        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=False),
        ):
            first = self.env.check_privileges()
        self.assertEqual(first, (False, False, "Non-privilege Mode"))

        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=True),
        ):
            second = self.env.check_privileges()

        self.assertEqual(second, first)

    def test_refresh_bypasses_stale_cache(self):
        """The install path must be able to force a live re-probe instead
        of trusting a stale boot-time negative."""
        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=False),
        ):
            self.env.check_privileges()

        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=True),
        ):
            refreshed = self.env.check_privileges(refresh=True)

        self.assertEqual(refreshed, (False, True, "Rish Mode"))

    def test_refresh_updates_the_cache_for_subsequent_plain_calls(self):
        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=False),
        ):
            self.env.check_privileges()

        with (
            patch("src.environment.subprocess.run", return_value=_completed(1)),
            patch("src.environment.rish_available", return_value=True),
        ):
            self.env.check_privileges(refresh=True)

        with patch("src.environment.subprocess.run", return_value=_completed(1)):
            later = self.env.check_privileges()

        self.assertEqual(later, (False, True, "Rish Mode"))

    def test_force_flags_bypass_probing_entirely(self):
        with patch("src.environment.subprocess.run") as mock_run:
            self.assertEqual(
                self.env.check_privileges(force_root=True),
                (True, False, "Root Mode"),
            )
            self.assertEqual(
                self.env.check_privileges(force_rish=True),
                (False, True, "Rish Mode"),
            )
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
