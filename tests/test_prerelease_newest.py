"""Pre-release mode must follow the newest release of any channel."""
from src.assets import AssetsManager
from src.config import config
from src.sources import pick_newest_release, sources_mgr


def rel(tag, pre=False, draft=False, assets=("x.mpp",)):
    return {"tag_name": tag, "prerelease": pre, "draft": draft,
            "assets": [{"name": a} for a in assets]}


def test_stable_newer_than_last_dev_wins():
    data = [rel("v1.23.0"), rel("v1.22.0"), rel("v1.22.0-dev.1", pre=True)]
    assert pick_newest_release(data)["tag_name"] == "v1.23.0"
    assert AssetsManager._select_github_release(data, True)["tag_name"] == "v1.23.0"


def test_newer_dev_wins_over_older_stable():
    data = [rel("v2-dev.3", pre=True), rel("v1.0")]
    assert pick_newest_release(data)["tag_name"] == "v2-dev.3"


def test_drafts_and_assetless_releases_skipped():
    data = [rel("d", draft=True), rel("empty", assets=()), rel("ok", pre=True)]
    assert pick_newest_release(data)["tag_name"] == "ok"


def test_empty_or_bad_payload():
    assert pick_newest_release([]) is None
    assert pick_newest_release({"message": "rate limited"}) is None


def test_stable_mode_still_skips_prereleases():
    data = [rel("v2-dev.3", pre=True), rel("v1.0")]
    assert AssetsManager._select_github_release(data, False)["tag_name"] == "v1.0"


def test_json_branch_follows_chosen_release_not_toggle():
    url = "https://raw.githubusercontent.com/o/r/refs/heads/main/patches-list.json"
    config.set("USE_PRE_RELEASE", "on")
    assert "/refs/heads/main/" in sources_mgr.get_effective_json_url("Anddea", url, False)
    assert "/refs/heads/dev/" in sources_mgr.get_effective_json_url("Anddea", url, True)
    assert "/refs/heads/dev/" in sources_mgr.get_effective_json_url("Anddea", url)
