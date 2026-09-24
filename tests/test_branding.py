"""
EnhanciPy branding regression tests.

Pins two rebrand contracts that a plausible regression could silently break:

1. The in-TUI header (`CyberHeader`, shown on every screen) is a single
   centered line reading "·· EnhanciPy - modded by jair-00 ··" — no
   lightning bolts, no leftover two-line "#header-subtitle" variant.
2. The Specs screen's changelog falls back to the bundled CHANGELOG.md
   section for the current version when the GitHub release API is
   unreachable, instead of showing upstream Enhancify's release notes or a
   blank "not available" placeholder.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")
os.environ.setdefault("ENHANCIPY_DEP_BOOTSTRAP", "0")

from textual.widgets import Label

from src.environment import env
from src.tui.app import EnhancifyApp
from src.tui.screens.specs import bundled_changelog


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestHeaderBranding(unittest.TestCase):
    def test_header_is_one_centered_enhancipy_line(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(40, 25)) as pilot:
                await pilot.pause()
                app.push_screen("main_menu_screen")
                await pilot.pause()
                label = app.screen.query_one("#header-title", Label)
                text = str(label.render())
                strip = label.render_line(0)
                return (
                    text,
                    label.size.height,
                    label.size.width,
                    strip.text,
                    len(list(app.screen.query("#header-subtitle"))),
                )

        text, height, width, line_text, subtitle_count = _run_async(scenario())

        self.assertEqual(text, "·· EnhanciPy - modded by jair-00 ··")
        self.assertNotIn("⚡", text)
        self.assertNotIn("Enhancify", text)
        self.assertEqual(height, 1)
        self.assertEqual(width, 36)

        leading = len(line_text) - len(line_text.lstrip(" "))
        trailing = len(line_text) - len(line_text.rstrip(" "))
        self.assertLessEqual(abs(leading - trailing), 1)

        self.assertEqual(subtitle_count, 0)


class TestSpecsChangelogFallback(unittest.TestCase):
    def test_specs_falls_back_to_bundled_changelog(self):
        class _FailingResponse:
            status_code = 404

            def json(self):
                return {}

        current_version = env.get_version()
        expected_section = bundled_changelog(current_version)
        marker = expected_section.splitlines()[0]

        async def scenario():
            app = EnhancifyApp()
            with patch(
                "src.tui.screens.specs.requests.get",
                return_value=_FailingResponse(),
            ):
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    app.push_screen("specs_screen")
                    await pilot.pause()
                    for _ in range(20):
                        await pilot.pause(0.05)
                        label = app.screen.query_one("#changelog-label", Label)
                        text = str(label.render())
                        if marker in text:
                            break
                    return text

        text = _run_async(scenario())

        self.assertIn(marker, text)
        self.assertIn(current_version, text)


if __name__ == "__main__":
    unittest.main()
