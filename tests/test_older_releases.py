"""Older Versions: listing recent .mpp releases, downloading one, and the import handoff."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

from src.assets import AssetsManager, PatchRelease
from src.sources import SourceInfo, SourcesManager
from src.utils import DownloadResult


class MockResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _rel(tag: str, *, pre: bool = False, draft: bool = False, asset: str | None = None) -> Dict[str, Any]:
    name = asset if asset is not None else f"patches-{tag.lstrip('v')}.mpp"
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": pre,
        "published_at": "2026-03-04T05:06:07Z",
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://x/notes.txt", "size": 1},
            {"name": name, "browser_download_url": f"https://x/{tag}/{name}", "size": 1234},
        ],
    }


PAYLOAD: List[Dict[str, Any]] = [
    _rel("v9.9", draft=True),
    _rel("v3-dev.1", pre=True),
    _rel("v2.1", asset="patches-2.1.jar"),
    _rel("v2.0"),
    _rel("v2-dev.1", pre=True),
    *[_rel(f"v1.{n}") for n in (5, 4, 3, 2, 1, 0)],
]


def make_mpp(path: Path, manifest_text: str) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", manifest_text)
        zf.writestr("dummy.txt", "x")
    return path


class TestFetchRecentPatchReleases(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.am = AssetsManager(workspace_dir=Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def _fetch(self, response=None, side_effect=None, **kw):
        with mock.patch("src.assets.requests.get", return_value=response, side_effect=side_effect) as g:
            out = self.am.fetch_recent_patch_releases("o/r", **kw)
        return out, g

    def test_stable_skips_drafts_prereleases_and_non_mpp(self):
        out, get = self._fetch(MockResponse(PAYLOAD), want_prerelease=False)
        self.assertEqual([r.tag for r in out], ["v2.0", "v1.5", "v1.4", "v1.3", "v1.2"])
        first = out[0]
        self.assertEqual(first.url, "https://x/v2.0/patches-2.0.mpp")
        self.assertEqual(first.asset_name, "patches-2.0.mpp")
        self.assertEqual((first.size, first.published, first.prerelease), (1234, "2026-03-04", False))
        self.assertIn("per_page=100", get.call_args.args[0])

    def test_prerelease_channel(self):
        out, _ = self._fetch(MockResponse(PAYLOAD), want_prerelease=True)
        self.assertEqual([r.tag for r in out], ["v3-dev.1", "v2-dev.1"])
        self.assertTrue(all(r.prerelease for r in out))

    def test_failures_return_none(self):
        for resp, effect in (
            (MockResponse([], 403), None),
            (None, Exception("boom")),
            (MockResponse({"message": "nope"}), None),
        ):
            with self.subTest(status=getattr(resp, "status_code", None), effect=effect):
                out, _ = self._fetch(resp, effect, want_prerelease=False)
                self.assertIsNone(out)

    def test_no_mpp_assets_is_empty_not_none(self):
        out, _ = self._fetch(MockResponse([_rel("v1.0", asset="p.jar")]), want_prerelease=False)
        self.assertEqual(out, [])


class TestDownloadPatchRelease(unittest.TestCase):
    REL = PatchRelease("v1.0", "2026-03-04", False, "patches-1.0.mpp", "https://x/p.mpp", 10)

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.am = AssetsManager(workspace_dir=Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_ok_returns_path_in_scratch_dir_and_wipes_previous(self):
        with mock.patch("src.assets.tempfile.gettempdir", return_value=self._td.name), mock.patch(
            "src.assets.download_file_ex", return_value=DownloadResult.OK
        ) as dl:
            stale = Path(self._td.name) / "enhancipy-releases" / "old.mpp"
            stale.parent.mkdir()
            stale.write_text("old")
            out = self.am.download_patch_release(self.REL)
        self.assertEqual(out, Path(self._td.name) / "enhancipy-releases" / "patches-1.0.mpp")
        self.assertFalse(stale.exists())
        self.assertEqual(dl.call_args.args[:3], (self.REL.url, out, 10))

    def test_error_returns_none(self):
        with mock.patch("src.assets.tempfile.gettempdir", return_value=self._td.name), mock.patch(
            "src.assets.download_file_ex", return_value=DownloadResult.ERROR
        ):
            self.assertIsNone(self.am.download_patch_release(self.REL))


class TestOlderReleasesUI(unittest.TestCase):
    def test_download_hands_file_to_import_name_prompt(self):
        from textual.widgets import ListView

        from src.tui.app import EnhancifyApp
        from src.tui.screens.main_menu import MainMenuScreen
        from src.tui.screens.older_releases import OlderReleasesScreen
        from src.tui.screens.source_select import SourceSelectScreen
        from src.tui.widgets.dialogs import InputDialog

        rels = [
            PatchRelease("v1.0.0", "2026-03-04", False, "patches-1.0.0.mpp", "https://x/a", 100),
            PatchRelease("v0.9.0", "2026-02-01", False, "patches-0.9.0.mpp", "https://x/b", 90),
        ]

        async def _run():
            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                mpp = make_mpp(
                    td / "patches-1.0.0.mpp",
                    "Manifest-Version: 1.0\r\nName: Src Patches\r\nVersion: 1.0.0\r\nPatcher-Version: 1.15.1\r\n",
                )
                sm = SourcesManager(td)
                app = EnhancifyApp()
                async with app.run_test(size=(80, 30)) as pilot:
                    for _ in range(300):
                        if isinstance(app.screen, MainMenuScreen):
                            break
                        await pilot.pause(0.02)
                    with mock.patch("src.tui.screens.source_select.sources_mgr", sm), mock.patch(
                        "src.tui.screens.older_releases.assets_mgr.fetch_recent_patch_releases",
                        return_value=rels,
                    ), mock.patch(
                        "src.tui.screens.older_releases.assets_mgr.download_patch_release",
                        return_value=mpp,
                    ):
                        picker = SourceSelectScreen()
                        app.push_screen(picker)
                        await pilot.pause(0.1)
                        app.push_screen(
                            OlderReleasesScreen(SourceInfo("Src", "o/r")),
                            picker._on_older_release_downloaded,
                        )
                        await pilot.pause(0.3)
                        lv = app.screen.query_one("#releases-list", ListView)
                        self.assertEqual(len(lv.children), 2)

                        app.screen.on_list_view_selected(
                            mock.Mock(item=lv.children[0])
                        )
                        await pilot.pause(0.2)
                        await pilot.click("#btn-yes")
                        for _ in range(100):
                            if isinstance(app.screen, InputDialog):
                                break
                            await pilot.pause(0.05)
                        self.assertIsInstance(app.screen, InputDialog)
                        self.assertEqual(app.screen.query_one("#dialog-input").value, "Src v1.0.0")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
