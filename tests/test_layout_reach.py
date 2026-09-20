"""
Scroll-reachability regression test.

Before this fix, `.list-card` filled `height: 100%` and its `ListView` had a
fixed `min-height: 10`, so a themes list at 80x24 produced a virtual height
taller than the viewport with no way to reach the card below it, and long
list rows were rendered at the full text width instead of wrapping (making
them unreachable sideways too). This pins both fixes.
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Label, ListView

from src.tui.app import EnhancifyApp
from src.tui.widgets.content_container import ContentContainer


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestLayoutReach(unittest.TestCase):
    def test_theme_list_fits_viewport(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                app.push_screen("theme_select_screen")
                await pilot.pause()
                await pilot.pause()
                container = app.screen.query_one(ContentContainer)
                return container.virtual_size.height, container.region.height

        virtual_height, viewport_height = _run_async(scenario())
        self.assertLessEqual(virtual_height, viewport_height)

    def test_theme_row_label_wraps_on_narrow_screen(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(40, 25)) as pilot:
                await pilot.pause()
                app.push_screen("theme_select_screen")
                await pilot.pause()
                await pilot.pause()
                list_view = app.screen.query_one("#themes-list", ListView)
                label = list_view.query(Label).first()
                return label.virtual_size.height

        row_height = _run_async(scenario())
        self.assertGreaterEqual(row_height, 2)


if __name__ == "__main__":
    unittest.main()
