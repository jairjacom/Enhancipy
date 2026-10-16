"""Starter-pack seeding, active-source fallback and the Manage Sources hub."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.config import config
from src.sources import SourcesManager


def _entry(name: str, repo: str = "o/r") -> dict:
    return {"source": name, "repository": repo, "api": {"json": "", "version": None}}


def _write_pack(td: Path, names) -> None:
    (td / "sources.json").write_text(json.dumps([_entry(n) for n in names]), encoding="utf-8")


def _user_names(td: Path) -> list:
    return [e["source"] for e in json.loads((td / "user_sources.json").read_text(encoding="utf-8"))]


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestSeeding(unittest.TestCase):
    def test_fresh_seed(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["A", "B"])
            sm = SourcesManager(td)
            self.assertEqual(_user_names(td), ["A", "B"])
            self.assertEqual(json.loads((td / "seeded_sources.json").read_text()), ["A", "B"])
            got = sm.get_all_sources()
            self.assertEqual([s.source for s in got], ["A", "B"])
            self.assertFalse(any(s.is_local for s in got))

    def test_delete_sticks_and_new_starter_seeds_once(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["A", "B"])
            sm = SourcesManager(td)
            sm.delete_custom_source("A")
            SourcesManager(td)
            self.assertEqual(_user_names(td), ["B"])

            _write_pack(td, ["A", "B", "C"])
            SourcesManager(td)
            self.assertEqual(_user_names(td), ["B", "C"])
            SourcesManager(td)
            self.assertEqual(_user_names(td), ["B", "C"])

    def test_same_name_user_source_kept(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["A"])
            (td / "user_sources.json").write_text(json.dumps([_entry("a", "x/y")]), encoding="utf-8")
            SourcesManager(td)
            entries = json.loads((td / "user_sources.json").read_text())
            self.assertEqual([(e["source"], e["repository"]) for e in entries], [("a", "x/y")])
            self.assertIn("A", json.loads((td / "seeded_sources.json").read_text()))

    def test_local_source_name_blocks_starter(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["A"])
            (td / "local_sources.json").write_text(
                json.dumps([{"source": "A", "version": "1.0.0", "patcher_version": ""}]), encoding="utf-8"
            )
            SourcesManager(td)
            self.assertEqual(_user_names(td), [])

    def test_malformed_pack_seeds_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "sources.json").write_text("{", encoding="utf-8")
            SourcesManager(td)
            self.assertEqual(_user_names(td), [])

    def test_corrupt_user_file_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["A"])
            (td / "user_sources.json").write_text("{", encoding="utf-8")
            SourcesManager(td)
            self.assertEqual((td / "user_sources.json").read_text(), "{")
            self.assertFalse((td / "seeded_sources.json").exists())


class TestFallback(unittest.TestCase):
    def _sm(self, td, names):
        td = Path(td)
        (td / "sources.json").write_text("[]", encoding="utf-8")
        sm = SourcesManager(td)
        (td / "user_sources.json").write_text(json.dumps([_entry(n) for n in names]), encoding="utf-8")
        return sm

    def test_prefers_default(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self._sm(td, ["X", "Anddea"]).fallback_source(), "Anddea")

    def test_first_when_default_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self._sm(td, ["X", "Y"]).fallback_source(), "X")

    def test_default_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self._sm(td, []).fallback_source(), "Anddea")


class TestActiveSourceUI(unittest.TestCase):
    def test_startup_migrates_dropped_active_source(self):
        from src.tui.app import EnhancifyApp

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _write_pack(td, ["Anddea"])
            sm = SourcesManager(td)
            prev = config.settings.get("SOURCE")
            try:
                config.settings["SOURCE"] = "De-Vanced"
                with mock.patch("src.tui.app.sources_mgr", sm):
                    app = EnhancifyApp()
                self.assertEqual(config.get("SOURCE"), "Anddea")
                self.assertEqual(app.multi_sources, ["Anddea"])
            finally:
                config.settings["SOURCE"] = prev

    def test_hub_delete_of_active_source_resets_selection_and_picker(self):
        from src.tui.app import EnhancifyApp
        from src.tui.screens.main_menu import MainMenuScreen
        from src.tui.screens.source_select import SourceSelectScreen
        from textual.widgets import ListView

        async def _run():
            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                _write_pack(td, ["Anddea", "MorpheApp"])
                sm = SourcesManager(td)
                prev = config.settings.get("SOURCE")
                try:
                    config.settings["SOURCE"] = "MorpheApp"
                    with mock.patch("src.tui.app.sources_mgr", sm), mock.patch(
                        "src.tui.screens.custom_sources.sources_mgr", sm
                    ), mock.patch("src.tui.screens.source_select.sources_mgr", sm):
                        app = EnhancifyApp()
                        async with app.run_test(size=(100, 30)) as pilot:
                            for _ in range(300):
                                if isinstance(app.screen, MainMenuScreen):
                                    break
                                await pilot.pause(0.02)
                            app.multi_sources = ["MorpheApp"]
                            app.push_screen(SourceSelectScreen())
                            await pilot.pause(0.1)
                            app.push_screen("custom_sources_screen")
                            await pilot.pause(0.1)
                            hub = app.screen
                            hub.prompt_source_actions(sm.get_source("MorpheApp"))
                            await pilot.pause(0.1)
                            await pilot.click("#btn-yes")
                            await pilot.pause(0.1)
                            await pilot.click("#btn-ok")
                            await pilot.pause(0.1)
                            app.pop_screen()
                            await pilot.pause(0.2)

                            self.assertEqual(config.get("SOURCE"), "Anddea")
                            self.assertEqual(app.multi_sources, ["Anddea"])
                            lv = app.screen.query_one("#sources-list", ListView)
                            names = [getattr(i, "source_name", None) for i in lv.children]
                            self.assertEqual(names, ["Anddea"])
                finally:
                    config.settings["SOURCE"] = prev

        _run_async(_run())


if __name__ == "__main__":
    unittest.main()
