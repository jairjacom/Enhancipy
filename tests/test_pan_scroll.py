"""
Vertical wheel -> horizontal pan on sideways-only panels.

Termux maps a finger swipe to vertical wheel events only, so a panel that
overflows horizontally must treat those as horizontal scrolling, while
panels with vertical overflow keep scrolling vertically.
"""

from __future__ import annotations

import asyncio
import unittest

from textual import events
from textual.app import App
from textual.widgets import Label

from src.tui.widgets.pan_scroll import PanScroll


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _wheel(cls, widget):
    return cls(widget, 1, 1, 0, 0, 0, False, False, False, 1, 1)


class _Host(App):
    CSS = "PanScroll { overflow-x: auto; }  /* as .detail-card does */"

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def compose(self):
        with PanScroll(id="pan"):
            yield Label(self._text)


WIDE = "x" * 200  # one wide line: overflows sideways only
TALL_AND_WIDE = "\n".join("x" * 200 for _ in range(60))


class TestPanScroll(unittest.TestCase):
    def _drive(self, text, event_cls, times=1):
        async def go():
            app = _Host(text)
            async with app.run_test(size=(40, 10)) as pilot:
                pan = app.query_one("#pan", PanScroll)
                await pilot.pause()
                for _ in range(times):
                    pan.post_message(_wheel(event_cls, pan))
                    await pilot.pause()
                return pan.scroll_x, pan.scroll_y, pan.max_scroll_x

        return _run_async(go())

    def test_swipe_up_and_down_pan_a_sideways_only_panel(self):
        x, y, _ = self._drive(WIDE, events.MouseScrollDown, times=2)
        self.assertEqual((x, y), (2 * PanScroll.PAN_STEP, 0))

    def test_opposite_swipe_pans_back_and_clamps_at_left_edge(self):
        x, _, _ = self._drive(WIDE, events.MouseScrollUp, times=3)
        self.assertEqual(x, 0)

    def test_pan_clamps_at_right_edge(self):
        _, _, max_x = self._drive(WIDE, events.MouseScrollDown, times=0)
        x, _, _ = self._drive(WIDE, events.MouseScrollDown, times=max_x)
        self.assertEqual(x, max_x)

    def test_panel_with_vertical_overflow_keeps_vertical_scroll(self):
        x, y, _ = self._drive(TALL_AND_WIDE, events.MouseScrollDown, times=2)
        self.assertEqual(x, 0)
        self.assertGreater(y, 0)


if __name__ == "__main__":
    unittest.main()
