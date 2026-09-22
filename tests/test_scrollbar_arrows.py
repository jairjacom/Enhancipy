"""
Scrollbar arrow decoration regression test.

Every scrollbar in the app renders through ScrollBar.renderer, a class
attribute installed in src/tui/app.py to ArrowScrollBarRender. This pins
the segment-level glyph placement (unit tests against the render_bar
override directly) and the end-to-end wiring (renderer installed + arrows
visible in a real screenshot).
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from rich.color import Color

from src.tui.app import EnhancifyApp
from src.tui.scrollbar import ArrowScrollBarRender
from src.tui.widgets.content_container import ContentContainer
from textual.scrollbar import ScrollBar


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestScrollbarArrowsUnit(unittest.TestCase):
    def test_vertical_bar_has_arrow_ends(self):
        back = Color.parse("#101010")
        bar = Color.parse("#00ff7f")
        rendered = ArrowScrollBarRender.render_bar(
            size=10,
            virtual_size=100,
            window_size=20,
            position=0,
            thickness=2,
            vertical=True,
            back_color=back,
            bar_color=bar,
        )
        segments = rendered.segments
        self.assertEqual(segments[0].text, "▲▲")
        self.assertEqual(segments[-1].text, "▼▼")
        self.assertEqual(segments[0].style.meta, {"@mouse.down": "scroll_up"})
        self.assertEqual(segments[-1].style.meta, {"@mouse.down": "scroll_down"})
        self.assertEqual(segments[0].style.color, bar)

    def test_horizontal_bar_has_arrow_ends(self):
        back = Color.parse("#101010")
        bar = Color.parse("#00ff7f")
        rendered = ArrowScrollBarRender.render_bar(
            size=40,
            virtual_size=200,
            window_size=40,
            position=0,
            thickness=1,
            vertical=False,
            back_color=back,
            bar_color=bar,
        )
        segments = rendered.segments
        self.assertEqual(segments[0].text, "◀")
        self.assertEqual(segments[39].text, "▶")
        self.assertEqual(segments[0].style.meta, {"@mouse.down": "scroll_up"})
        self.assertEqual(segments[39].style.meta, {"@mouse.down": "scroll_down"})

    def test_short_bar_undecorated(self):
        rendered = ArrowScrollBarRender.render_bar(
            size=2,
            virtual_size=100,
            window_size=1,
            position=0,
            thickness=1,
            vertical=True,
        )
        segments = rendered.segments
        self.assertNotEqual(segments[0].text, "▲")
        self.assertNotEqual(segments[-1].text, "▼")

    def test_no_overflow_undecorated(self):
        rendered = ArrowScrollBarRender.render_bar(
            size=10,
            virtual_size=10,
            window_size=0,
            position=0,
            thickness=1,
            vertical=True,
        )
        texts = "".join(segment.text for segment in rendered.segments)
        self.assertNotIn("▲", texts)
        self.assertNotIn("▼", texts)


class TestScrollbarArrowsEndToEnd(unittest.TestCase):
    def test_renderer_installed_and_visible_in_app(self):
        self.assertIs(ScrollBar.renderer, ArrowScrollBarRender)

        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(20, 10)) as pilot:
                await pilot.pause()
                app.push_screen("theme_select_screen")
                for _ in range(5):
                    await pilot.pause(0.05)
                container = app.screen.query_one(ContentContainer)
                overflow = container.show_vertical_scrollbar
                screenshot = app.export_screenshot()
                return overflow, screenshot

        overflow, screenshot = _run_async(scenario())
        self.assertTrue(overflow, "precondition: container must show a vertical scrollbar")
        self.assertIn("▲", screenshot)
        self.assertIn("▼", screenshot)


if __name__ == "__main__":
    unittest.main()
