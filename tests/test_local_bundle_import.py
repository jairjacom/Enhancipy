"""Importing a local .mpp patch bundle as a persistent local source."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from src.assets import (
    AssetsManager,
    BundleManifest,
    cli_compatible,
)
from src.config import config
from src.sources import SourcesManager, sanitize_local_source_name


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def make_cli(path: Path, patcher_version: str | None, mtime: float | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        if patcher_version is not None:
            zf.writestr("app/morphe/patcher/version.properties", f"version={patcher_version}\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def make_mpp(path: Path, manifest_text: str | None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        if manifest_text is not None:
            zf.writestr("META-INF/MANIFEST.MF", manifest_text)
        zf.writestr("dummy.txt", "x")
    return path


MANIFEST = (
    "Manifest-Version: 1.0\r\n"
    "Name: Jair Patches\r\n"
    "Version: 1.0.0-dev.4\r\n"
    "Patcher-Version: 1.15.1\r\n"
)


class TestManifest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.am = AssetsManager(workspace_dir=self.td)

    def tearDown(self):
        self._td.cleanup()

    def test_reads_fields_and_wrapped_continuation(self):
        text = (
            "Manifest-Version: 1.0\r\n"
            "Name: A Very Long Patch Bundle Name That Wraps Across Two Manifes\r\n"
            " t Lines\r\n"
            "Version: 2.0.0\r\n"
            "Patcher-Version: 1.14.1\r\n"
        )
        m = self.am.read_bundle_manifest(make_mpp(self.td / "a.mpp", text))
        self.assertEqual(m.name, "A Very Long Patch Bundle Name That Wraps Across Two Manifest Lines")
        self.assertEqual((m.version, m.patcher_version), ("2.0.0", "1.14.1"))

    def test_name_falls_back_to_stem_and_patcher_optional(self):
        m = self.am.read_bundle_manifest(
            make_mpp(self.td / "fallback.mpp", "Manifest-Version: 1.0\nVersion: 3\n")
        )
        self.assertEqual((m.name, m.patcher_version), ("fallback", ""))

    def test_rejects_non_zip_missing_manifest_missing_version(self):
        bad = self.td / "bad.mpp"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(ValueError) as c:
            self.am.read_bundle_manifest(bad)
        self.assertEqual(str(c.exception), "Not a valid patch file (not a zip archive).")

        with self.assertRaises(ValueError) as c:
            self.am.read_bundle_manifest(make_mpp(self.td / "nomf.mpp", None))
        self.assertIn("no manifest", str(c.exception))

        with self.assertRaises(ValueError) as c:
            self.am.read_bundle_manifest(
                make_mpp(self.td / "nover.mpp", "Manifest-Version: 1.0\nName: X\n")
            )
        self.assertIn("no Version", str(c.exception))


class TestCliSelection(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.am = AssetsManager(workspace_dir=self.td)
        a = self.am.assets_dir
        self.old = make_cli(a / "CLI-v1.old.jar", "1.14.0", 1000)
        self.mid = make_cli(a / "CLI-v1.mid.jar", "1.15.1-dev.7", 2000)
        self.new = make_cli(a / "CLI-v2.jar", "2.0.0", 3000)
        make_cli(a / "CLI-v0.noprops.jar", None, 9000)  # ignored: no version

    def tearDown(self):
        self._td.cleanup()

    def test_compatibility_rule(self):
        self.assertTrue(cli_compatible("1.15.1-dev.7", "1.15.1"))
        self.assertTrue(cli_compatible("1.15.1", "1.14.1"))
        self.assertFalse(cli_compatible("1.14.0", "1.15.0"))
        self.assertFalse(cli_compatible("2.0.0", "1.15.0"))  # major differs
        self.assertFalse(cli_compatible("", "1.15.0"))

    def test_selection(self):
        self.assertEqual(self.am.select_cli_for_bundle("1.15.1"), (self.mid, True))
        # highest compatible, not the oldest/newest-by-mtime
        self.assertEqual(self.am.select_cli_for_bundle("1.14.1"), (self.mid, True))
        # nothing compatible -> best (highest) candidate, flagged
        self.assertEqual(self.am.select_cli_for_bundle("1.16.0"), (self.new, False))
        # unknown bundle version -> newest mtime among readable jars
        self.assertEqual(self.am.select_cli_for_bundle(""), (self.new, True))

    def test_no_candidates(self):
        for j in self.am.assets_dir.glob("CLI-*.jar"):
            j.unlink()
        self.assertEqual(self.am.select_cli_for_bundle("1.15.1"), (None, False))

    def test_adopt_cached_cli_copies_compatible_jar(self):
        for j in self.am.assets_dir.glob("CLI-*.jar"):
            j.unlink()
        cache = self.am.cli_cache_dir / "SomeSrc"
        cache.mkdir()
        make_cli(cache / "CLI-v1.mid.jar", "1.15.1-dev.7")
        make_cli(cache / "CLI-v1.old.jar", "1.14.0")
        got = self.am.adopt_cached_cli_for_bundle("1.15.0")
        self.assertEqual(got, self.am.assets_dir / "CLI-v1.mid.jar")
        self.assertTrue(got.exists())
        self.assertIsNone(self.am.adopt_cached_cli_for_bundle("1.16.0"))


class TestStaging(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.am = AssetsManager(workspace_dir=self.td)

    def tearDown(self):
        self._td.cleanup()

    def test_replaces_old_bundle_keeps_apps_cache(self):
        d = self.am.assets_dir / "Jair"
        d.mkdir()
        for n in ("Patches-v1.mpp", "Patches-v1.json", "Apps-v1.json"):
            (d / n).write_text("old")
        src = self.td / "in.mpp"
        src.write_bytes(b"bundle")
        out = self.am.stage_local_bundle(src, "Jair", BundleManifest("J", "2.0.0", "1.15.1"))
        self.assertEqual(out, d / "Patches-v2.0.0.mpp")
        self.assertEqual(out.read_bytes(), b"bundle")
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["Apps-v1.json", "Patches-v2.0.0.mpp"])

    def test_source_inside_dest_dir_rejected(self):
        d = self.am.assets_dir / "Jair"
        d.mkdir()
        src = d / "Patches-v1.mpp"
        src.write_bytes(b"x")
        with self.assertRaises(ValueError):
            self.am.stage_local_bundle(src, "Jair", BundleManifest("J", "1", ""))
        self.assertTrue(src.exists())  # not deleted before the check

    def test_remove_local_bundle(self):
        d = self.am.assets_dir / "Jair"
        d.mkdir()
        (d / "Patches-v1.mpp").write_text("x")
        self.am.remove_local_bundle("Jair")
        self.assertFalse(d.exists())
        self.am.remove_local_bundle("")  # must not wipe assets/
        self.assertTrue(self.am.assets_dir.exists())


class TestLocalSources(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        (self.td / "sources.json").write_text(
            json.dumps([{"source": "Anddea", "repository": "a/b", "api": {"json": "", "version": None}}])
        )
        self.sm = SourcesManager(self.td)

    def tearDown(self):
        self._td.cleanup()

    def test_remote_name_collision_rejected(self):
        ok, msg = self.sm.save_local_source("anddea", "1.0.0", "1.15.1")
        self.assertFalse(ok)
        self.assertIn("already exists as a remote source", msg)
        self.assertFalse(self.sm.local_sources_file.exists())

    def test_invalid_and_reserved_names(self):
        self.assertIn("may only use", self.sm.validate_local_source_name("../x"))
        self.assertIn("reserved", self.sm.validate_local_source_name("Morphe-Data"))
        self.assertIsNone(self.sm.validate_local_source_name("Jair Patches"))

    def test_resave_case_variant_keeps_single_entry(self):
        self.assertTrue(self.sm.save_local_source("Jair", "1.0.0", "1.15.1")[0])
        self.assertTrue(self.sm.save_local_source("jair", "1.1.0", "1.15.1")[0])
        locals_ = [s for s in self.sm.get_all_sources() if s.is_local]
        self.assertEqual([(s.source, s.bundle_version) for s in locals_], [("jair", "1.1.0")])
        self.assertEqual(self.sm.get_local_source("JAIR").patcher_version, "1.15.1")

    def test_local_flag_and_delete(self):
        self.sm.save_local_source("Jair", "1.0.0", "1.15.1")
        s = self.sm.get_local_source("Jair")
        self.assertTrue(s.is_local)
        self.assertFalse(s.is_custom)
        self.assertEqual(s.bundle_version, "1.0.0")
        self.assertIsNone(self.sm.get_local_source("Anddea"))
        self.sm.delete_local_source("Jair")
        self.assertIsNone(self.sm.get_local_source("Jair"))

    def test_update_tags_skips_local(self):
        self.sm.save_local_source("Jair", "1.0.0", "1.15.1")
        seen = []

        def fake(src):
            seen.append(src.source)
            return "v1", "v1"

        with mock.patch.object(self.sm, "fetch_source_tags", side_effect=fake):
            self.sm.update_tags(specific_source="Jair")
            self.sm.update_tags(specific_source="Anddea")
        self.assertEqual(seen, ["Anddea"])

    def test_sanitize_name(self):
        self.assertEqual(sanitize_local_source_name("Jair/Patches!"), "Jair-Patches")
        self.assertEqual(sanitize_local_source_name("***"), "Imported")


class TestLocalReleaseInfo(unittest.TestCase):
    def test_offline_release_info_for_staged_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            sm = SourcesManager(td)
            am = AssetsManager(workspace_dir=td)
            make_cli(am.assets_dir / "CLI-v1.18.1-dev.5.jar", "1.15.1-dev.7")
            src = make_mpp(td / "in.mpp", MANIFEST)
            manifest = am.read_bundle_manifest(src)
            am.stage_local_bundle(src, "Jair", manifest)
            sm.save_local_source("Jair", manifest.version, manifest.patcher_version)

            with mock.patch("src.assets.sources_mgr", sm), mock.patch(
                "src.assets.requests.get", side_effect=AssertionError("network used")
            ):
                rel = am.fetch_source_release_info("Jair")
                self.assertEqual(rel.patches_version, "v1.0.0-dev.4")
                self.assertEqual(rel.patches_ext, "mpp")
                self.assertEqual(rel.cli_version, "v1.18.1-dev.5")
                self.assertEqual(rel.json_url, "")
                self.assertEqual((rel.patches_size, rel.cli_size), (0, 0))

                # Wiped assets -> None (AppSelect shows the re-import message)
                am.remove_local_bundle("Jair")
                self.assertIsNone(am.fetch_source_release_info("Jair"))


class TestImportUI(unittest.TestCase):
    def test_finish_import_activates_source_and_opens_app_select(self):
        from src.tui.app import EnhancifyApp
        from src.tui.screens.app_select import AppSelectScreen
        from src.tui.screens.main_menu import MainMenuScreen
        from src.tui.screens.source_select import SourceSelectScreen

        async def _run():
            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                sm = SourcesManager(td)
                prev = config.settings.get("SOURCE")
                app = EnhancifyApp()
                try:
                    async with app.run_test(size=(80, 24)) as pilot:
                        for _ in range(300):
                            if isinstance(app.screen, MainMenuScreen):
                                break
                            await pilot.pause(0.02)
                        with mock.patch("src.tui.screens.source_select.sources_mgr", sm), mock.patch(
                            "src.tui.screens.source_select.assets_mgr.stage_local_bundle",
                            return_value=td / "x.mpp",
                        ), mock.patch(
                            "src.tui.screens.app_select.assets_mgr.fetch_source_release_info",
                            return_value=None,
                        ):
                            screen = SourceSelectScreen(is_patch_flow=True)
                            app.push_screen(screen)
                            await pilot.pause(0.1)
                            screen._finish_import(
                                td / "in.mpp", "Jair", BundleManifest("Jair Patches", "1.0.0-dev.4", "1.15.1")
                            )
                            await pilot.pause(0.2)
                            self.assertEqual(config.get("SOURCE"), "Jair")
                            self.assertEqual(
                                [e["source"] for e in json.loads(sm.local_sources_file.read_text())],
                                ["Jair"],
                            )
                            self.assertTrue(any(isinstance(s, AppSelectScreen) for s in app.screen_stack))
                finally:
                    config.settings["SOURCE"] = prev

        _run_async(_run())


if __name__ == "__main__":
    unittest.main()
