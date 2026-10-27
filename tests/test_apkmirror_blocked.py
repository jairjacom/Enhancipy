"""
APKMirror Cloudflare-challenge handling and the browser handoff.

APKMirror serves some apps (e.g. Instagram) behind a managed JS challenge
(HTTP 403 + `cf-mitigated: challenge`) that plain HTTP clients cannot pass.
The scraper must surface that as APKMirrorBlocked instead of "no versions",
build a version list from the unchallenged app_exists API, and pick up the
file the user downloads in the browser from the shared Downloads folder.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

from src import apkmirror
from src.antisplit import ExtractedAppMeta
from src.apkmirror import (
    APKMirrorBlocked,
    APKMirrorScraper,
    ScrapedVersion,
    snapshot_downloads,
    wait_for_browser_download,
)
from src.config import ConfigManager


class FakeResp:
    def __init__(self, status=200, headers=None, text="", payload=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = text
        self._payload = payload

    def json(self):
        return self._payload


CHALLENGE = FakeResp(403, {"cf-mitigated": "challenge"}, "<html>cType: 'managed'</html>")

UPLOADS_HTML = (
    '<div class="listWidget"><div class="appRow">'
    '<h5><a class="fontBlack" href="/apk/x/app-1-2-3-release/">App 1.2.3</a></h5>'
    "</div></div>"
)

# Modelled on the real Instagram app_exists response.
INSTAGRAM_ENTRY = {
    "pname": "com.instagram.android",
    "exists": True,
    "app": {"name": "Instagram", "link": "/apk/instagram/instagram-instagram/"},
    "release": {
        "version": "453.0.0.55.79",
        "link": "/apk/instagram/instagram-instagram/instagram-instagram-453-0-0-55-79-release/",
    },
    "apks": [
        {"version_code": "385914237", "arches": ["arm64-v8a"], "minapi": "28",
         "link": "/v/385914237-android-apk-download/"},
        {"version_code": "385914272", "arches": ["arm64-v8a"], "minapi": "40",
         "link": "/v/385914272-android-apk-download/"},
        {"version_code": "385914283", "arches": ["arm64-v8a"], "minapi": "28",
         "link": "/v/385914283-android-apk-download/"},
        {"version_code": "385914999", "arches": ["x86"], "minapi": "28",
         "link": "/v/385914999-android-apk-download/"},
    ],
}


class _ScraperCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.scraper = APKMirrorScraper(workspace_dir=self.workspace)
        patcher = mock.patch("src.apkmirror.config", ConfigManager(self.workspace))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def patch_env(self, arch="arm64-v8a", sdk="34"):
        fake = SimpleNamespace(get_arch=lambda: arch, getprop=lambda *a, **k: sdk)
        p = mock.patch("src.apkmirror.env", fake)
        p.start()
        self.addCleanup(p.stop)


class TestChallengeDetection(_ScraperCase):
    def test_all_pages_challenged_raises(self):
        with mock.patch("src.apkmirror.requests.get", return_value=CHALLENGE):
            with self.assertRaises(APKMirrorBlocked):
                self.scraper.fetch_versions_list("instagram-instagram", force_refresh=True)

    def test_blocked_result_is_not_cached(self):
        with mock.patch("src.apkmirror.requests.get", return_value=CHALLENGE):
            with self.assertRaises(APKMirrorBlocked):
                self.scraper.fetch_versions_list("instagram-instagram", force_refresh=True)
        self.assertIsNone(self.scraper.read_cached_versions("instagram-instagram", 1))

    def test_partial_block_returns_scraped_versions(self):
        def fake_get(url, **kw):
            return FakeResp(200, text=UPLOADS_HTML) if "/page/1/" in url else CHALLENGE

        with mock.patch("src.apkmirror.requests.get", side_effect=fake_get):
            res = self.scraper.fetch_versions_list("twitter", force_refresh=True)
        self.assertEqual([v.version for v in res], ["1.2.3"])

    def test_plain_403_is_not_a_challenge(self):
        with mock.patch("src.apkmirror.requests.get", return_value=FakeResp(403)):
            self.assertEqual(self.scraper.fetch_versions_list("twitter", force_refresh=True), [])

    def test_download_link_challenged_raises(self):
        with mock.patch("src.apkmirror.requests.get", return_value=CHALLENGE):
            with self.assertRaises(APKMirrorBlocked):
                self.scraper.scrape_download_link("/apk/x/app-1-2-3-release/")

    def test_download_link_404_returns_none(self):
        with mock.patch("src.apkmirror.requests.get", return_value=FakeResp(404)):
            self.assertIsNone(self.scraper.scrape_download_link("/apk/x/app-1-2-3-release/"))


class TestFetchBrowserVersions(_ScraperCase):
    def _post(self, status=200, entries=None):
        payload = {"data": [INSTAGRAM_ENTRY] if entries is None else entries}
        return mock.patch("src.apkmirror.requests.post", return_value=FakeResp(status, payload=payload))

    def test_latest_uses_best_matching_variant(self):
        self.patch_env()
        with self._post():
            res = self.scraper.fetch_browser_versions("com.instagram.android", [])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].version, "453.0.0.55.79")
        self.assertEqual(res[0].tag, "[STABLE]")
        # arch match, minapi 40 > sdk 34 filtered, x86 ignored, highest code wins
        self.assertEqual(res[0].url, "https://www.apkmirror.com/v/385914283-android-apk-download/")

    def test_older_supported_version_gets_release_page(self):
        self.patch_env()
        with self._post():
            res = self.scraper.fetch_browser_versions("com.instagram.android", ["452.1.0.53.64"])
        by_version = {v.version: v for v in res}
        old = by_version["452.1.0.53.64"]
        self.assertEqual(old.tag, "[RECOMMENDED]")
        self.assertEqual(
            old.url,
            "https://www.apkmirror.com/apk/instagram/instagram-instagram/"
            "instagram-instagram-452-1-0-53-64-release/",
        )

    def test_latest_in_supported_is_recommended(self):
        self.patch_env()
        with self._post():
            res = self.scraper.fetch_browser_versions("com.instagram.android", ["453.0.0.55.79"])
        self.assertEqual([(v.version, v.tag) for v in res], [("453.0.0.55.79", "[RECOMMENDED]")])

    def test_no_arch_match_falls_back_to_release_page(self):
        self.patch_env(arch="mips")
        with self._post():
            res = self.scraper.fetch_browser_versions("com.instagram.android", [])
        self.assertTrue(res[0].url.endswith("instagram-instagram-453-0-0-55-79-release/"))

    def test_non_200_returns_empty(self):
        self.patch_env()
        with self._post(status=500):
            self.assertEqual(self.scraper.fetch_browser_versions("com.instagram.android", []), [])

    def test_unknown_package_returns_empty(self):
        self.patch_env()
        with self._post(entries=[{"pname": "com.instagram.android", "exists": False}]):
            self.assertEqual(self.scraper.fetch_browser_versions("com.instagram.android", []), [])


def _meta(pkg, path, version="1.0", ext="apk"):
    return ExtractedAppMeta(pkg_name=pkg, app_name=pkg, version_name=version, extension=ext, file_path=path)


class TestWaitForBrowserDownload(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.cancel = threading.Event()
        p = mock.patch.object(apkmirror.antisplit_mgr, "ensure_aapt2", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def _wait(self, extract, before=None, timeout=3.0, poll=0.01):
        with mock.patch.object(apkmirror.antisplit_mgr, "extract_metadata", side_effect=extract):
            return wait_for_browser_download(
                "com.app", self.cancel, [self.dir], before or {}, timeout=timeout, poll_interval=poll
            )

    def test_preexisting_file_is_ignored(self):
        old = self.dir / "old.apk"
        old.write_bytes(b"x" * 10)
        before = snapshot_downloads([self.dir])
        calls = []
        res = self._wait(lambda p: calls.append(p) or _meta("com.app", p), before, timeout=0.3)
        self.assertIsNone(res)
        self.assertEqual(calls, [])

    def test_partial_download_suffix_is_ignored(self):
        (self.dir / "app.apk.crdownload").write_bytes(b"x" * 10)
        self.assertEqual(snapshot_downloads([self.dir]), {})

    def test_other_package_is_ignored(self):
        (self.dir / "other.apkm").write_bytes(b"x" * 10)
        res = self._wait(lambda p: _meta("com.other", p, ext="apkm"), timeout=0.3)
        self.assertIsNone(res)

    def test_returns_only_after_size_is_stable(self):
        target = self.dir / "app.apk"
        target.write_bytes(b"x")
        seen_sizes = []
        writer_done = threading.Event()

        def grow():
            for _ in range(10):
                with open(target, "ab") as f:
                    f.write(b"y" * 100)
                time.sleep(0.05)
            writer_done.set()

        threading.Thread(target=grow, daemon=True).start()

        def extract(p):
            seen_sizes.append(p.stat().st_size)
            return _meta("com.app", p)

        # Poll slower than the writer's write interval so any two polls straddle a write.
        res = self._wait(extract, poll=0.2)
        self.assertIsNotNone(res)
        self.assertTrue(writer_done.is_set(), "returned while the file was still growing")
        self.assertEqual(seen_sizes, [1 + 10 * 100])

    def test_cancel_returns_promptly(self):
        self.cancel.set()
        start = time.monotonic()
        self.assertIsNone(self._wait(lambda p: _meta("com.app", p), timeout=30))
        self.assertLess(time.monotonic() - start, 2)


class TestAdoptBrowserDownload(_ScraperCase):
    def test_moves_file_and_writes_data(self):
        src = self.workspace / "dl.apkm"
        src.write_bytes(b"z" * 7)
        target = self.scraper.adopt_browser_download("Instagram", "1.2.3", src, "apkm")
        self.assertEqual(target, self.workspace / "apps" / "Instagram" / "1.2.3.apkm")
        self.assertFalse(src.exists())
        data = (target.parent / ".data").read_text()
        self.assertIn("APP_FORMAT='BUNDLE'", data)
        self.assertIn("APP_EXT='apkm'", data)
        self.assertIn("APP_SIZE='7'", data)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _wait_for(pred, pilot, timeout: float = 15.0):
    elapsed = 0.0
    while elapsed < timeout:
        if pred():
            await pilot.pause(0.15)
            return True
        await pilot.pause(0.02)
        elapsed += 0.02
    return False


class TestVersionSelectBlockedFlow(unittest.TestCase):
    SELECTED = {
        "pkgName": "com.instagram.android",
        "appName": "Instagram",
        "apkmirrorAppName": "instagram-instagram",
        "versions": [],
    }

    def _drive(self, click, expect_browser_fetch):
        from src.tui.app import EnhancifyApp
        from src.tui.screens.version_select import VersionSelectScreen
        from src.tui.widgets.dialogs import ConfirmDialog
        from textual.widgets import ListView

        browser_versions = [ScrapedVersion("453.0.0.55.79", "[STABLE]", "https://www.apkmirror.com/apk/x/")]

        async def _run():
            app = EnhancifyApp()
            with mock.patch.object(
                apkmirror.apkmirror_scraper, "fetch_versions_list", side_effect=APKMirrorBlocked("x")
            ), mock.patch.object(
                apkmirror.apkmirror_scraper, "fetch_browser_versions", return_value=browser_versions
            ) as fbv:
                async with app.run_test(size=(100, 30)) as pilot:
                    app.selected_app = dict(self.SELECTED)
                    app.push_screen("version_select_screen")
                    self.assertTrue(
                        await _wait_for(lambda: isinstance(app.screen, ConfirmDialog), pilot),
                        "blocked dialog did not appear",
                    )
                    self.assertIn("APKMirror Blocked", str(app.screen.query_one(".dialog-title").render()))
                    await pilot.click(click)
                    await pilot.pause(0.5)
                    screen = next(s for s in app.screen_stack if isinstance(s, VersionSelectScreen))
                    return fbv.called, screen.browser_mode, len(list(screen.query_one("#versions-list", ListView).children))

        called, browser_mode, items = _run_async(_run())
        self.assertEqual(called, expect_browser_fetch)
        return browser_mode, items

    def test_use_browser_lists_api_versions(self):
        browser_mode, items = self._drive("#btn-yes", True)
        self.assertTrue(browser_mode)
        self.assertEqual(items, 1)

    def test_back_does_not_enter_browser_mode(self):
        browser_mode, _ = self._drive("#btn-no", False)
        self.assertFalse(browser_mode)


class TestBrowserHandoffEndToEnd(unittest.TestCase):
    """Pick a version in browser mode: browser opens, the file dropped into
    Downloads is moved into apps/<App>/, and Patch Selection opens."""

    def test_downloaded_file_is_adopted_and_flow_continues(self):
        import src.tui.screens.version_select as vs
        from src.tui.app import EnhancifyApp
        from src.tui.screens.patch_select import PatchSelectScreen
        from src.tui.widgets.dialogs import ConfirmDialog, DownloadProgressModal

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        downloads = tmp / "Download"
        downloads.mkdir()
        dropped = downloads / "ig.apk"
        opened = []

        def fake_open(url):
            opened.append(url)

            def drop():
                time.sleep(0.5)
                dropped.write_bytes(b"a" * 50)
                time.sleep(0.2)
                dropped.write_bytes(b"a" * 100)

            threading.Thread(target=drop, daemon=True).start()
            return True

        version = ScrapedVersion("453.0.0.55.79", "[STABLE]", "https://www.apkmirror.com/v/x-android-apk-download/")
        meta = _meta("com.instagram.android", dropped, version="453.0.0.55.79")
        scraper = apkmirror.apkmirror_scraper

        async def _run():
            app = EnhancifyApp()
            with mock.patch.object(scraper, "fetch_versions_list", side_effect=APKMirrorBlocked("x")), \
                    mock.patch.object(scraper, "fetch_browser_versions", return_value=[version]), \
                    mock.patch.object(scraper, "apps_dir", tmp / "apps"), \
                    mock.patch.object(vs, "open_in_browser", fake_open), \
                    mock.patch.object(vs, "browser_download_dirs", return_value=[downloads]), \
                    mock.patch.object(apkmirror.antisplit_mgr, "ensure_aapt2", return_value=True), \
                    mock.patch.object(apkmirror.antisplit_mgr, "extract_metadata", return_value=meta), \
                    mock.patch.object(vs.config, "is_on", return_value=False):
                async with app.run_test(size=(100, 30)) as pilot:
                    app.selected_app = dict(TestVersionSelectBlockedFlow.SELECTED)
                    app.push_screen("version_select_screen")
                    self.assertTrue(await _wait_for(lambda: isinstance(app.screen, ConfirmDialog), pilot))
                    await pilot.click("#btn-yes")
                    screen = next(s for s in app.screen_stack if isinstance(s, vs.VersionSelectScreen))
                    self.assertTrue(await _wait_for(lambda: screen.browser_mode and screen.versions_list, pilot))
                    screen.download_and_proceed(version)
                    self.assertTrue(
                        await _wait_for(lambda: isinstance(app.screen, DownloadProgressModal), pilot)
                    )
                    self.assertTrue(
                        await _wait_for(lambda: isinstance(app.screen, PatchSelectScreen), pilot, 30)
                    )
                    return app.selected_app["apk_path"]

        apk_path = _run_async(_run())
        self.assertEqual(opened, [version.url])
        self.assertEqual(apk_path, tmp / "apps" / "Instagram" / "453.0.0.55.79.apk")
        self.assertTrue(apk_path.exists())
        self.assertFalse(dropped.exists(), "file should be moved out of Downloads")


if __name__ == "__main__":
    unittest.main()
