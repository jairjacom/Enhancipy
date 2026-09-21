"""
Version-downgrade conflict dialog regression tests.

rish-install.sh reports INSTALL_FAILED_VERSION_DOWNGRADE via
install_failure_code.txt when `pm install` refuses to downgrade an app in
place. install_or_export() surfaces that as InstallResult.conflict, and
PatchProgressScreen must turn it into a Yes/No ConfirmDialog (green Yes, red
No, both legible in every theme) rather than a generic error dialog — and on
Yes, drive AppInstaller.uninstall_and_reinstall() instead of leaving the user
stuck. This pins both the button styling and the conflict -> dialog -> retry
wiring end to end.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Button

from src.installer import CONFLICT_VERSION_DOWNGRADE, InstallResult
from src.theme import set_current_theme
from src.tui.app import EnhancifyApp
from src.tui.screens.patch_progress import PatchProgressScreen
from src.tui.widgets.dialogs import ConfirmDialog, MessageDialog


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


class TestDowngradeDialog(unittest.TestCase):
    def test_confirm_dialog_success_button_is_green_in_every_theme(self):
        async def scenario():
            set_current_theme("cyber_green")
            app = EnhancifyApp()
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                app.push_screen(
                    ConfirmDialog("t", "m", yes_class="btn-success", no_class="btn-danger")
                )
                await pilot.pause()
                yes_before = app.screen.query_one("#btn-yes").styles.border_top[1].hex.lower()
                no_before = app.screen.query_one("#btn-no").styles.border_top[1].hex.lower()

                app.apply_theme("dracula")
                await pilot.pause()

                yes_after = app.screen.query_one("#btn-yes").styles.border_top[1].hex.lower()
                return yes_before, no_before, yes_after

        yes_before, no_before, yes_after = _run_async(scenario())

        self.assertEqual(yes_before, "#2ea043")
        self.assertEqual(no_before, "#ff4444")
        self.assertEqual(yes_after, "#2ea043")

    def test_downgrade_conflict_prompts_then_runs_uninstall_reinstall(self):
        tmp_apk = tempfile.NamedTemporaryFile(suffix=".apk", delete=False)
        tmp_apk.close()
        apk_path = Path(tmp_apk.name)

        conflict_result = InstallResult(
            False,
            "Rish installation failed: INSTALL_FAILED_VERSION_DOWNGRADE: Downgrade "
            "detected: Update version code 312270001 is older than current 312271001",
            conflict=CONFLICT_VERSION_DOWNGRADE,
            exported_name="TestApp-1.0-TestSrc",
        )
        reinstall_result = InstallResult(
            True, "TestApp installed successfully via Rish with Dex Optimization!"
        )

        async def scenario():
            with (
                patch.object(PatchProgressScreen, "start_patching_process", lambda self: None),
                patch(
                    "src.tui.screens.patch_progress.app_installer.install_or_export",
                    return_value=conflict_result,
                ),
                patch(
                    "src.tui.screens.patch_progress.app_installer.uninstall_and_reinstall",
                    return_value=reinstall_result,
                ) as mock_reinstall,
            ):
                app = EnhancifyApp()
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    app.selected_app = {
                        "appName": "TestApp",
                        "version": "1.0",
                        "pkgName": "com.test.app",
                    }
                    screen = PatchProgressScreen()
                    app.push_screen(screen)
                    await pilot.pause()
                    screen.output_apk = apk_path

                    screen.action_install()

                    found_confirm = await _wait_for(
                        pilot, lambda: isinstance(app.screen, ConfirmDialog)
                    )
                    self.assertTrue(found_confirm, "ConfirmDialog never appeared")

                    yes_button = app.screen.query_one("#btn-yes", Button)
                    yes_label = str(yes_button.label)
                    yes_classes = set(yes_button.classes)

                    await pilot.click("#btn-yes")

                    found_message = await _wait_for(
                        pilot,
                        lambda: isinstance(app.screen, MessageDialog)
                        and app.screen.dialog_title == "Installation Result",
                    )
                    self.assertTrue(found_message, "Final MessageDialog never appeared")
                    final_message = app.screen.message

                mock_reinstall.assert_called_once()
                reinstall_args = mock_reinstall.call_args[0]
                return yes_label, yes_classes, final_message, reinstall_args

        try:
            yes_label, yes_classes, final_message, reinstall_args = _run_async(scenario())
        finally:
            apk_path.unlink(missing_ok=True)

        self.assertIn("Yes", yes_label)
        self.assertIn("btn-success", yes_classes)
        self.assertIn("installed successfully", final_message)
        self.assertEqual(reinstall_args, ("TestApp", "com.test.app", "TestApp-1.0-TestSrc"))


if __name__ == "__main__":
    unittest.main()
