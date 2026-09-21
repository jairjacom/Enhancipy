"""
Privilege-detection regression tests (src/environment.py).

check_privileges() memoizes its result for the lifetime of the Environment
instance. That is fine for cheap header re-renders but is wrong for the
actual install decision: rish/Shizuku can attach *after* the very first
(possibly too-early) probe, and a stale negative must not be trusted at
install time. refresh=True exists to bypass the cache; this pins that
contract so it can't silently regress back to "always cached".
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from src.environment import Environment


def _completed(returncode: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode)


class TestPrivilegeCaching(unittest.TestCase):
    def setUp(self):
        self.env = Environment(workspace_dir=None)

    def test_plain_call_returns_cached_result_even_when_state_changed(self):
        """First probe finds nothing; rish becomes available later; an
        uncached-unaware caller must still see the original snapshot."""
        with patch("src.environment.subprocess.run") as mock_run:
            mock_run.return_value = _completed(1)  # su and rish both fail
            first = self.env.check_privileges()
        self.assertEqual(first, (False, False, "Non-privilege Mode"))

        with patch("src.environment.subprocess.run") as mock_run:
            mock_run.return_value = _completed(0)  # rish now available
            second = self.env.check_privileges()

        self.assertEqual(second, first)

    def test_refresh_bypasses_stale_cache(self):
        """The install path must be able to force a live re-probe instead
        of trusting a stale boot-time negative."""
        with patch("src.environment.subprocess.run") as mock_run:
            mock_run.return_value = _completed(1)
            self.env.check_privileges()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "rish":
                return _completed(0)
            return _completed(1)

        with patch("src.environment.subprocess.run", side_effect=fake_run):
            refreshed = self.env.check_privileges(refresh=True)

        self.assertEqual(refreshed, (False, True, "Rish Mode"))

    def test_refresh_updates_the_cache_for_subsequent_plain_calls(self):
        with patch("src.environment.subprocess.run") as mock_run:
            mock_run.return_value = _completed(1)
            self.env.check_privileges()

        def fake_run(cmd, **kwargs):
            if cmd[0] == "rish":
                return _completed(0)
            return _completed(1)

        with patch("src.environment.subprocess.run", side_effect=fake_run):
            self.env.check_privileges(refresh=True)

        with patch("src.environment.subprocess.run") as mock_run:
            mock_run.return_value = _completed(1)
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
