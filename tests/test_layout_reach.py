"""
Row-wrap reachability regression test.

Before this fix, long list rows were rendered at the full text width
instead of wrapping, making their text unreachable sideways on narrow
screens. This pins that fix.

(The companion "list never needs scrolling" invariant this file used to pin
was superseded by the uniform-autoheight-windows feature: `.list-card
ListView` now deliberately grows up to 60vh, which can require scrolling to
reach content below it by design — see tests/test_base_screen.py for the
regression coverage of that viewport-relative cap.)
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Label, ListView

from src.tui.app import EnhancifyApp


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestLayoutReach(unittest.TestCase):
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
