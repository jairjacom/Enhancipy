"""
Uniform window chrome & auto-height regression test.

Before this fix, every screen hand-repeated the same CyberHeader / ContentContainer
/ Footer boilerplate (with drift in a few screens), and list height caps were fixed
row counts that ignored viewport size. This pins both: every registered screen (plus
FilePickerScreen, which is pushed as an instance rather than registered) shares the
BaseScreen window, and a list's rendered height grows/shrinks with the terminal
height (e.g. the Termux on-screen keyboard resizing the pty).
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import ListView

from src.tui.app import EnhancifyApp
from src.tui.screens.base import BaseScreen
from src.tui.screens.file_picker import FilePickerScreen


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestBaseScreen(unittest.TestCase):
    def test_every_screen_uses_base_window(self):
        for name, cls in EnhancifyApp.SCREENS.items():
            if name == "boot_screen":
                continue
            self.assertTrue(
                issubclass(cls, BaseScreen),
                f"{name} ({cls.__name__}) does not use the shared BaseScreen window",
            )
        self.assertTrue(issubclass(FilePickerScreen, BaseScreen))

    def test_list_auto_adjusts_to_viewport(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                app.push_screen(FilePickerScreen(Path(".")))
                await pilot.pause()
                await pilot.pause()
                list_view = app.screen.query_one("#file-list", ListView)
                tall_height = list_view.region.height

                await pilot.resize_terminal(80, 10)
                await pilot.pause()
                await pilot.pause()
                short_height = list_view.region.height

                return tall_height, short_height

        tall_height, short_height = _run_async(scenario())
        # 60vh at 24 rows == 14; at 10 rows == 6 (pinned from the live smoke run).
        self.assertEqual(tall_height, 14)
        self.assertEqual(short_height, 6)
        self.assertLess(short_height, tall_height)
        self.assertGreaterEqual(short_height, 4)  # min-height floor


if __name__ == "__main__":
    unittest.main()
