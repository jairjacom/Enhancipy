"""
Version-list ordering regression tests (src/apkmirror.py).

fetch_versions_list scrapes pages 1..N concurrently and merges results in
thread-completion order via as_completed, so both a fresh scrape and a
legacy cached list can come back scrambled. order_versions() is the single
choke point that fixes this: up to 3 newest [RECOMMENDED] versions pinned
at the top (newest first), then everything else newest->oldest. These
tests pin that contract so a regression (e.g. dropping the final sort, or
pinning more/fewer than 3) is caught.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.apkmirror import APKMirrorScraper, ScrapedVersion, order_versions
from src.config import ConfigManager


class TestOrderVersionsPure(unittest.TestCase):
    def test_two_recommended_pinned_newest_first(self):
        versions = [
            ScrapedVersion("21.10.00", "[STABLE]", "u1"),
            ScrapedVersion("19.09.39", "[RECOMMENDED]", "u2"),
            ScrapedVersion("22.01.10", "[STABLE]", "u3"),
            ScrapedVersion("21.13.164", "[RECOMMENDED]", "u4"),
            ScrapedVersion("18.00.01", "[STABLE]", "u5"),
        ]
        result = order_versions(versions)
        self.assertEqual([v.version for v in result[:2]], ["21.13.164", "19.09.39"])
        rest = [v.version for v in result[2:]]
        self.assertEqual(rest, ["22.01.10", "21.10.00", "18.00.01"])

    def test_single_recommended_pinned_alone(self):
        versions = [
            ScrapedVersion("22.01.10", "[STABLE]", "u1"),
            ScrapedVersion("19.09.39", "[RECOMMENDED]", "u2"),
            ScrapedVersion("18.00.01", "[STABLE]", "u3"),
        ]
        result = order_versions(versions)
        self.assertEqual(result[0].version, "19.09.39")
        self.assertEqual(result[0].tag, "[RECOMMENDED]")
        self.assertEqual([v.version for v in result[1:]], ["22.01.10", "18.00.01"])

    def test_only_top_three_recommended_pinned(self):
        versions = [
            ScrapedVersion("10.00.00", "[RECOMMENDED]", "u1"),
            ScrapedVersion("40.00.00", "[RECOMMENDED]", "u2"),
            ScrapedVersion("30.00.00", "[RECOMMENDED]", "u3"),
            ScrapedVersion("20.00.00", "[RECOMMENDED]", "u4"),
            ScrapedVersion("25.00.00", "[STABLE]", "u5"),
        ]
        result = order_versions(versions)
        self.assertEqual(
            [v.version for v in result[:3]], ["40.00.00", "30.00.00", "20.00.00"]
        )
        # 4th recommended (10.00.00) stays in the body at its desc position,
        # still tagged [RECOMMENDED], not pinned.
        body = result[3:]
        self.assertEqual([v.version for v in body], ["25.00.00", "10.00.00"])
        self.assertEqual(body[-1].tag, "[RECOMMENDED]")

    def test_installed_not_pinned(self):
        versions = [
            ScrapedVersion("30.00.00", "[STABLE]", "u1"),
            ScrapedVersion("20.00.00", "[INSTALLED]", "u2"),
            ScrapedVersion("10.00.00", "[STABLE]", "u3"),
        ]
        result = order_versions(versions)
        self.assertEqual([v.version for v in result], ["30.00.00", "20.00.00", "10.00.00"])
        self.assertEqual(result[1].tag, "[INSTALLED]")

    def test_deeper_version_tuple_sorts_newer(self):
        versions = [
            ScrapedVersion("21.13", "[STABLE]", "u1"),
            ScrapedVersion("21.13.164", "[STABLE]", "u2"),
            ScrapedVersion("21.12.99", "[STABLE]", "u3"),
        ]
        result = order_versions(versions)
        self.assertEqual(
            [v.version for v in result], ["21.13.164", "21.13", "21.12.99"]
        )


class TestFetchVersionsListOrdering(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.scraper = APKMirrorScraper(workspace_dir=self.workspace)
        self.config_patch = patch("src.apkmirror.config", ConfigManager(self.workspace))
        self.config_patch.start()

    def tearDown(self):
        self.config_patch.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _assert_ordered(self, res):
        self.assertEqual(res[0].version, "21.13.164")
        self.assertEqual(res[0].tag, "[RECOMMENDED]")
        self.assertEqual(res[1].version, "19.09.39")
        self.assertEqual(res[1].tag, "[RECOMMENDED]")
        rest = [v.version for v in res[2:]]
        self.assertEqual(rest, sorted(rest, key=lambda v: [int(p) for p in v.split(".")], reverse=True))

    def test_fresh_scrape_orders_and_dedupes(self):
        # Two pages, deliberately scrambled/interleaved, with an overlapping
        # duplicate version to pin dedupe alongside ordering.
        page_1 = [
            {"version": "20.05.05", "tag": "[STABLE]", "url": "u-20.05.05"},
            {"version": "21.13.164", "tag": "[STABLE]", "url": "u-21.13.164"},
            {"version": "18.01.01", "tag": "[STABLE]", "url": "u-18.01.01"},
        ]
        page_2 = [
            {"version": "19.09.39", "tag": "[STABLE]", "url": "u-19.09.39"},
            # duplicate across pages: must be deduped, keeping first-seen url
            {"version": "21.13.164", "tag": "[STABLE]", "url": "u-21.13.164-dup"},
            {"version": "22.00.00", "tag": "[STABLE]", "url": "u-22.00.00"},
        ]

        def fake_scrape(app_name, page_num):
            return {1: page_2, 2: page_1}.get(page_num, [])

        with patch.object(self.scraper, "scrape_versions_page", side_effect=fake_scrape):
            res = self.scraper.fetch_versions_list(
                "youtube", supported_versions=["21.13.164", "19.09.39"]
            )

        self._assert_ordered(res)
        # dedupe kept exactly one entry per version
        self.assertEqual(len(res), len({v.version for v in res}))

    def test_legacy_scrambled_cache_orders_on_read(self):
        scrambled_cache = [
            {"version": "18.01.01", "tag": "[STABLE]", "url": "u1"},
            {"version": "21.13.164", "tag": "[STABLE]", "url": "u2"},
            {"version": "22.00.00", "tag": "[STABLE]", "url": "u3"},
            {"version": "19.09.39", "tag": "[STABLE]", "url": "u4"},
        ]
        self.scraper.write_cached_versions("youtube", scrambled_cache, 5)

        # No scrape_versions_page patch: force_refresh=False must hit the
        # cache and never touch the network.
        res = self.scraper.fetch_versions_list(
            "youtube",
            supported_versions=["21.13.164", "19.09.39"],
            force_refresh=False,
        )

        self._assert_ordered(res)


if __name__ == "__main__":
    unittest.main()
