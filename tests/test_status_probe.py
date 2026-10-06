"""
Lazy privilege/network probe regression tests.

BaseScreen.compose() used to run env.check_privileges() (su -c exit, timeout
5, then the rish probe, timeout 8) and env.check_network() (two 0.8s socket
dials) synchronously on the UI thread on every screen mount — freezing the
app on open. compose() must now render the last known values (or
"Checking...") instantly, while on_mount() refreshes them in a background
worker and recomposes the header/status-bar/unmount-button once the probe
resolves. The Install button's live re-probe (refresh=True) must likewise
run inside the install worker thread, not on the UI thread before the
"Installing APK" modal appears.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Button, Label

from src.environment import env
from src.installer import InstallResult
from src.tui.app import EnhancifyApp
from src.tui.screens.main_menu import MainMenuScreen
from src.tui.screens.patch_progress import PatchProgressScreen
from src.tui.widgets.dialogs import MessageDialog, ProgressModal
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
                        app.screen.query_one(CyberHeader).query_one("#badge-mode", Label).render()
                    )
                    self.assertIn("Checking...", header_text)
                    mode_badge = app.screen.query_one(CyberHeader).query_one("#badge-mode", Label)
                    for cls in ("badge-green", "badge-cyan", "badge-purple"):
                        self.assertFalse(mode_badge.has_class(cls))
                    self.assertFalse(
                        app.screen.query_one("#btn-unmount", Button).display
                    )

                    gate.set()

                    def _resolved() -> bool:
                        try:
                            text = str(
                                app.screen.query_one(CyberHeader)
                                .query_one("#badge-mode", Label)
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
                    mode_badge = app.screen.query_one(CyberHeader).query_one("#badge-mode", Label)
                    self.assertTrue(mode_badge.has_class("badge-green"))
                    status_bar_text = str(
                        app.screen.query_one(CyberStatusBar)
                        .query_one(".line-mode", Label)
                        .render()
                    )
                    self.assertIn("Root Mode", status_bar_text)
                    net_text = str(
                        app.screen.query_one(CyberHeader).query_one("#badge-net", Label).render()
                    )
                    self.assertIn("Online", net_text)
                    net_badge = app.screen.query_one(CyberHeader).query_one("#badge-net", Label)
                    self.assertTrue(net_badge.has_class("badge-green"))
                    self.assertFalse(net_badge.has_class("badge-cyan"))

        _run_async(scenario())

    def test_install_press_returns_before_live_reprobe(self):
        gate = self._gate
        recorded_refresh_flags = []

        def fake_check_privileges(*args, refresh=False, **kwargs):
            recorded_refresh_flags.append(refresh)
            if refresh:
                gate.wait(5)
            return (False, True, "Rish Mode")

        tmp_apk = tempfile.NamedTemporaryFile(suffix=".apk", delete=False)
        tmp_apk.close()
        apk_path = Path(tmp_apk.name)

        async def scenario():
            with (
                patch.object(
                    PatchProgressScreen, "start_patching_process", lambda self: None
                ),
                patch(
                    "src.tui.screens.patch_progress.app_installer.install_or_export",
                    return_value=InstallResult(True, "ok"),
                ) as mock_install,
                patch.object(env, "check_privileges", side_effect=fake_check_privileges),
                patch.object(env, "check_network", return_value=(True, True, "Online")),
            ):
                app = EnhancifyApp()
                async with app.run_test(size=(80, 30)) as pilot:
                    found = await _wait_for(
                        pilot, lambda: isinstance(app.screen, MainMenuScreen)
                    )
                    self.assertTrue(found, "MainMenuScreen never appeared")

                    app.selected_app = {
                        "appName": "TestApp",
                        "version": "1.0",
                        "pkgName": "com.test.app",
                    }
                    screen = PatchProgressScreen()
                    app.push_screen(screen)
                    await pilot.pause()
                    screen.output_apk = apk_path

                    t0 = time.monotonic()
                    screen.action_install()
                    elapsed = time.monotonic() - t0
                    self.assertLess(elapsed, 1.0, "action_install blocked on the live re-probe")

                    found_modal = await _wait_for(
                        pilot, lambda: isinstance(app.screen, ProgressModal)
                    )
                    self.assertTrue(found_modal, "ProgressModal never appeared")

                    gate.set()

                    found_message = await _wait_for(
                        pilot,
                        lambda: isinstance(app.screen, MessageDialog)
                        and app.screen.dialog_title == "Installation Result",
                    )
                    self.assertTrue(found_message, "Final MessageDialog never appeared")

                self.assertIn(True, recorded_refresh_flags)
                self.assertEqual(mock_install.call_args[0][5:7], (False, True))

        try:
            _run_async(scenario())
        finally:
            apk_path.unlink(missing_ok=True)


class TestHeaderBadgeClasses(unittest.TestCase):
    def test_mode_badge_class(self):
        from src.tui.widgets.header import mode_badge_class

        cases = [
            ("Root Mode", "badge-green"),
            ("Rish Mode", "badge-cyan"),
            ("Non-privilege Mode", "badge-purple"),
            ("Checking...", ""),
        ]
        for label, expected in cases:
            with self.subTest(label=label):
                self.assertEqual(mode_badge_class(label), expected)

    def test_net_badge_class(self):
        from src.tui.widgets.header import net_badge_class

        cases = [
            ("Online", "badge-green"),
            ("Partial (Apkmirror Down)", "badge-yellow"),
            ("Partial (Github Down)", "badge-yellow"),
            ("Offline", "badge-red"),
            ("Checking...", ""),
        ]
        for status, expected in cases:
            with self.subTest(status=status):
                self.assertEqual(net_badge_class(status), expected)


if __name__ == "__main__":
    unittest.main()
