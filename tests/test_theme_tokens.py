"""
Theme-token regression test.

EnhanciPy drives every theme from a single ~14-value `$enh-*` token palette
(src/theme.py) instead of per-theme CSS class duplication. This pins the
mechanism that makes a live theme switch actually repaint a mounted screen:
`EnhancifyApp.apply_theme()` must update `self._theme_id`, re-resolve the
stylesheet via `refresh_css()`, and refresh already-rendered widgets so
`$enh-*` markup doesn't stay stale. If any of those steps regress, this
test fails while the plain "themes exist" unit test would not.
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from src.tui.app import EnhancifyApp


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestThemeTokens(unittest.TestCase):
    def test_theme_switch_recolors_mounted_screen(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                app.push_screen("main_menu_screen")
                await pilot.pause()

                before_bg = app.screen.styles.background.hex
                before_accent = app.get_css_variables()["enh-accent"]

                app.apply_theme("dracula")
                await pilot.pause()

                after_bg = app.screen.styles.background.hex
                after_accent = app.get_css_variables()["enh-accent"]
                return before_bg, before_accent, after_bg, after_accent

        before_bg, before_accent, after_bg, after_accent = _run_async(scenario())

        self.assertNotEqual(before_bg, after_bg)
        self.assertEqual(after_bg, "#1E1F29")
        self.assertEqual(before_accent, "#00ff7f")
        self.assertEqual(after_accent, "#bd93f9")


if __name__ == "__main__":
    unittest.main()
