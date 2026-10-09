"""
Thin-line scrollbar regression test.

Every scrollbar in the app renders through ScrollBar.renderer, a class
attribute installed in src/tui/app.py to LineScrollBarRender. This pins
the segment-level glyph placement (unit tests against the render_bar
override directly) and the end-to-end wiring (renderer installed, one-cell
thickness, dot ends visible in a real screenshot, no arrow glyphs).
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from rich.color import Color
from textual.scrollbar import ScrollBar
from textual.widgets import ListView

from src.theme import contrast_ratio
from src.tui.app import EnhancifyApp
from src.tui.scrollbar import LineScrollBarRender, track_color
from src.tui.widgets.content_container import ContentContainer


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestScrollbarLineUnit(unittest.TestCase):
    def test_vertical_bar_is_thin_line_with_dot_ends(self):
        back = Color.parse("#0c0817")
        bar = Color.parse("#ff007f")
        segments = LineScrollBarRender.render_bar(
            size=10,
            virtual_size=100,
            window_size=20,
            position=0,
            thickness=1,
            vertical=True,
            back_color=back,
            bar_color=bar,
        ).segments
        self.assertEqual(len(segments), 10)
        self.assertEqual(segments[0].text, "•")
        self.assertEqual(segments[0].style.meta, {"@mouse.down": "scroll_up"})
        self.assertEqual(segments[0].style.color, bar)
        self.assertEqual(segments[1].text, "┃")
        self.assertEqual(segments[1].style.meta, {"@mouse.down": "grab"})
        track = track_color(back, bar)
        self.assertNotEqual(track, bar)
        self.assertGreaterEqual(contrast_ratio(track.get_truecolor().hex, "#0c0817"), 3.0)
        for i in range(2, 9):
            self.assertEqual(segments[i].text, "│")
            self.assertEqual(segments[i].style.color, track)
        self.assertEqual(segments[-1].text, "•")
        self.assertEqual(segments[-1].style.meta, {"@mouse.down": "scroll_down"})

    def test_vertical_thumb_follows_position(self):
        segments = LineScrollBarRender.render_bar(
            size=10,
            virtual_size=100,
            window_size=20,
            position=80,
            thickness=1,
            vertical=True,
            back_color=Color.parse("#0c0817"),
            bar_color=Color.parse("#ff007f"),
        ).segments
        self.assertEqual(segments[8].text, "┃")
        self.assertEqual(segments[0].text, "•")
        self.assertEqual(segments[1].text, "│")

    def test_horizontal_bar_is_thin_line_with_dot_ends(self):
        segments = LineScrollBarRender.render_bar(
            size=40,
            virtual_size=200,
            window_size=40,
            position=0,
            thickness=1,
            vertical=False,
            back_color=Color.parse("#0c0817"),
            bar_color=Color.parse("#ff007f"),
        ).segments
        self.assertEqual(segments[0].text, "•")
        self.assertEqual(segments[0].style.meta, {"@mouse.down": "scroll_up"})
        for i in range(1, 8):
            self.assertEqual(segments[i].text, "━")
        self.assertEqual(segments[8].text, "─")
        self.assertEqual(segments[39].text, "•")
        self.assertEqual(segments[39].style.meta, {"@mouse.down": "scroll_down"})

    def test_short_bar_has_no_dots(self):
        segments = LineScrollBarRender.render_bar(
            size=2,
            virtual_size=100,
            window_size=20,
            position=0,
            thickness=1,
            vertical=True,
            back_color=Color.parse("#0c0817"),
            bar_color=Color.parse("#ff007f"),
        ).segments
        self.assertNotIn("•", "".join(s.text for s in segments))

    def test_no_overflow_draws_nothing(self):
        segments = LineScrollBarRender.render_bar(
            size=10,
            virtual_size=10,
            window_size=0,
            position=0,
            thickness=1,
            vertical=True,
            back_color=Color.parse("#0c0817"),
            bar_color=Color.parse("#ff007f"),
        ).segments
        self.assertEqual("".join(s.text for s in segments).strip(" \n"), "")


class TestScrollbarLineEndToEnd(unittest.TestCase):
    def test_renderer_installed_and_visible_in_app(self):
        self.assertIs(ScrollBar.renderer, LineScrollBarRender)

        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(20, 10)) as pilot:
                await pilot.pause()
                app.push_screen("theme_select_screen")
                for _ in range(5):
                    await pilot.pause(0.05)
                container = app.screen.query_one(ContentContainer)
                overflow = container.show_vertical_scrollbar
                container_size = container.styles.scrollbar_size_vertical
                list_size = app.screen.query_one(ListView).styles.scrollbar_size_vertical
                screenshot = app.export_screenshot()
                return overflow, container_size, list_size, screenshot

        overflow, container_size, list_size, screenshot = _run_async(scenario())
        self.assertTrue(overflow, "precondition: container must show a vertical scrollbar")
        self.assertEqual(container_size, 1)
        self.assertEqual(list_size, 1)
        self.assertIn("•", screenshot)
        self.assertNotIn("▲", screenshot)
        self.assertNotIn("▼", screenshot)


if __name__ == "__main__":
    unittest.main()
