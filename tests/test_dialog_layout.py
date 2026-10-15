"""
Dialog sizing regression tests (40x20 portrait-ish screen).

Pins: dialog text wraps instead of being cut off; Input and Footer do not
paint scrollbar glyphs over their only row; dialog list regions never
collapse to 0 content rows; ProgressModal's spinner fits its dialog;
ChecklistDialog selection/save flow; comma_list_items routing rule.
"""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from textual.widgets import Button, Label, LoadingIndicator, SelectionList

from src.tui.app import EnhancifyApp
from src.tui.screens.options_edit import comma_list_items
from src.tui.widgets.dialogs import (
    ChecklistDialog,
    InputDialog,
    MessageDialog,
    ProgressModal,
    SelectDialog,
    ToggleSwitchDialog,
)

SIZE = (40, 20)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _screen_text(app) -> str:
    return "\n".join(s.text for s in app.screen._compositor.render_strips())


async def _push(app, pilot, screen, callback=None):
    app.push_screen(screen, callback)
    await pilot.pause()
    await pilot.pause()


class TestDialogLayout(unittest.TestCase):
    def test_message_dialog_text_wraps(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await _push(
                    app,
                    pilot,
                    MessageDialog(
                        "Installation Result",
                        "YouTube was installed successfully. The patched build was installed "
                        "alongside and keeps a different signature from the original app.",
                    ),
                )
                label = app.screen.query_one(".dialog-message", Label)
                return (
                    label.region.width,
                    label.parent.scrollable_content_region.width,
                    label.size.height,
                )

        width, avail, height = _run_async(scenario())
        self.assertLessEqual(width, avail)
        self.assertGreaterEqual(height, 3)

    def test_input_dialog_long_value_shows_tail(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                value = ", ".join([f"x{i:02d}" for i in range(91)] + ["zu"])
                await _push(app, pilot, InputDialog("T", "P", initial_value=value))
                app.screen.query_one("#dialog-input").focus()
                await pilot.pause()
                return _screen_text(app)

        self.assertIn("x90, zu", _run_async(scenario()))

    def test_select_dialog_scroll_region_has_rows(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await _push(app, pilot, SelectDialog("T", "P", [(f"Choice {i}", str(i)) for i in range(12)]))
                box = app.screen.query_one(".select-scroll")
                return box.show_vertical_scrollbar, box.scrollable_content_region.height

        scrolls, rows = _run_async(scenario())
        self.assertTrue(scrolls)
        self.assertGreaterEqual(rows, 3)

    def test_toggle_dialog_scroll_region_has_rows(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                options = [(f"k{i}", f"Option {i}", "long enough description to wrap twice") for i in range(12)]
                await _push(app, pilot, ToggleSwitchDialog("T", options, {}))
                box = app.screen.query_one("#toggle-scroll")
                return box.show_vertical_scrollbar, box.scrollable_content_region.height

        scrolls, rows = _run_async(scenario())
        self.assertTrue(scrolls)
        self.assertGreaterEqual(rows, 3)

    def test_checklist_dialog_layout_toggle_and_save(self):
        items = [f"c{i:02d}" for i in range(92)]

        async def scenario():
            app = EnhancifyApp()
            results: list = []
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await _push(app, pilot, ChecklistDialog("T", "P", items, items), results.append)
                sl = app.screen.query_one("#checklist", SelectionList)
                layout = (
                    app.focused is sl,
                    sl.show_vertical_scrollbar,
                    sl.scrollable_content_region.height,
                )
                await pilot.press("space")
                await pilot.pause()
                count = str(app.screen.query_one("#checklist-count", Label).render())
                app.screen.query_one("#btn-save", Button).press()
                await pilot.pause()
                await pilot.pause()
            return layout, count, results

        layout, count, results = _run_async(scenario())
        self.assertTrue(layout[0], "list must be auto-focused")
        self.assertTrue(layout[1])
        self.assertGreaterEqual(layout[2], 3)
        self.assertEqual(count, "91 of 92 selected")
        self.assertEqual(results, [items[1:]])

    def test_checklist_dialog_blocks_empty_save(self):
        items = [f"c{i:02d}" for i in range(92)]

        async def scenario():
            app = EnhancifyApp()
            results: list = []
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await _push(app, pilot, ChecklistDialog("T", "P", items, items), results.append)
                dlg = app.screen
                dlg.query_one("#checklist", SelectionList).deselect_all()
                await pilot.pause()
                dlg.query_one("#btn-save", Button).press()
                await pilot.pause()
                await pilot.pause()
                return (
                    isinstance(app.screen, MessageDialog),
                    results,
                    dlg in app.screen_stack,
                )

        is_msg, results, still_open = _run_async(scenario())
        self.assertTrue(is_msg)
        self.assertEqual(results, [])
        self.assertTrue(still_open)

    def test_footer_row_has_no_scrollbar_glyphs(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                return app.screen._compositor.render_strips()[-1].text

        last = _run_async(scenario())
        self.assertIn("Patch App", last)
        self.assertNotIn("━", last)

    def test_progress_modal_spinner_fits(self):
        async def scenario():
            app = EnhancifyApp()
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause()
                await _push(app, pilot, ProgressModal("T", "Running DEX Optimization via Rish..."))
                box = app.screen.query_one(".dialog-box")
                return box.show_vertical_scrollbar, app.screen.query_one(LoadingIndicator).region.height

        scrolls, spinner_h = _run_async(scenario())
        self.assertFalse(scrolls)
        self.assertEqual(spinner_h, 1)


class TestCommaListItems(unittest.TestCase):
    BASE = [f"l{i:02d}" for i in range(24)]

    def _opt(self, **over):
        joined = ", ".join(self.BASE)
        opt = {"type": "String", "values": {}, "default": joined, "value": joined}
        opt.update(over)
        return opt

    def test_default_tokens(self):
        self.assertEqual(comma_list_items(self._opt()), self.BASE)

    def test_custom_extra_tokens_are_appended(self):
        value = ", ".join(self.BASE) + ", zz"
        self.assertEqual(comma_list_items(self._opt(value=value)), self.BASE + ["zz"])

    def test_subset_value_adds_nothing(self):
        self.assertEqual(comma_list_items(self._opt(value="l05, l01")), self.BASE)

    def test_non_qualifying_options(self):
        cases = {
            "boolean": self._opt(type="Boolean"),
            "string array": self._opt(type="StringArray"),
            "preset values": self._opt(values={"A": "a"}),
            "single token": self._opt(default="abc"),
            "url": self._opt(default="https://a, b"),
            "empty token": self._opt(default="a,,b"),
            "no default": self._opt(default=None),
            "numbers": self._opt(default="3, 5, 10"),
        }
        for name, opt in cases.items():
            with self.subTest(name):
                self.assertIsNone(comma_list_items(opt))


if __name__ == "__main__":
    unittest.main()
