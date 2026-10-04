"""
Lazy privilege/network probe regression tests.

BaseScreen.compose() used to run env.check_privileges() (su -c exit, timeout
5, then the rish probe, timeout 8) and env.check_network() (two 0.8s socket
dials) synchronously on the UI thread on every screen mount — freezing the
app on open. compose() must now render the last known values (or
"Checking...") instantly, while on_mount() refreshes them in a background
worker and recomposes the header/status-bar/unmount-button once the probe
resolves.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Button, Label

from src.environment import env
from src.tui.app import EnhancifyApp
from src.tui.screens.main_menu import MainMenuScreen
from src.tui.widgets.header import CyberHeader
from src.tui.widgets.status_bar import CyberStatusBar


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _wait_for(pilot, predicate, attempts: int = 60, delay: float = 0.05) -> bool:
    for _ in range(attempts):
        await pilot.pause()
        if predicate():
            return True
        await asyncio.sleep(delay)
    return False


class TestStatusProbe(unittest.TestCase):
    def setUp(self):
        self._saved_privileges = env._cached_privileges
        self._saved_network = env._cached_network
        env._cached_privileges = None
        env._cached_network = None
        self._gate = threading.Event()

    def tearDown(self):
        self._gate.set()
        env._cached_privileges = self._saved_privileges
        env._cached_network = self._saved_network

    def test_screen_mounts_before_privilege_probe_and_updates_after(self):
        gate = self._gate

        def fake_check_privileges(*args, **kwargs):
            gate.wait(5)
            return (True, False, "Root Mode")

        async def scenario():
            with (
                patch.object(env, "check_privileges", side_effect=fake_check_privileges),
                patch.object(env, "check_network", return_value=(True, True, "Online")),
            ):
                t0 = time.monotonic()
                app = EnhancifyApp()
                async with app.run_test(size=(80, 30)) as pilot:
                    found = await _wait_for(
                        pilot, lambda: isinstance(app.screen, MainMenuScreen)
                    )
                    self.assertTrue(found, "MainMenuScreen never appeared")
                    elapsed = time.monotonic() - t0
                    self.assertLess(elapsed, 2.0, "compose() blocked on the privilege probe")

                    # Still pending: gate is unset.
                    header_text = str(
                        app.screen.query_one(CyberHeader).query_one(".badge-green", Label).render()
                    )
                    self.assertIn("Checking...", header_text)
                    self.assertFalse(
                        app.screen.query_one("#btn-unmount", Button).display
                    )

                    gate.set()

                    def _resolved() -> bool:
                        try:
                            text = str(
                                app.screen.query_one(CyberHeader)
                                .query_one(".badge-green", Label)
                                .render()
                            )
                        except Exception:
                            return False
                        return "Root Mode" in text

                    resolved = await _wait_for(pilot, _resolved)
                    self.assertTrue(resolved, "header never picked up the resolved privilege")

                    self.assertTrue(
                        app.screen.query_one("#btn-unmount", Button).display
                    )
                    status_bar_text = str(
                        app.screen.query_one(CyberStatusBar)
                        .query_one(".line-mode", Label)
                        .render()
                    )
                    self.assertIn("Root Mode", status_bar_text)
                    net_text = str(
                        app.screen.query_one(CyberHeader).query_one(".badge-cyan", Label).render()
                    )
                    self.assertIn("Online", net_text)

        _run_async(scenario())


if __name__ == "__main__":
    unittest.main()
