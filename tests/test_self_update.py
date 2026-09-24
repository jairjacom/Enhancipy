"""Self-update regression tests (src/self_update.py).

Uses a local HTTP server instead of the real GitHub release/API so these
tests never depend on network access.
"""

from __future__ import annotations

import http.server
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.config import config
from src.self_update import SelfUpdater, is_newer


class _FixtureServer:
    """Threading HTTP server serving files out of a temp directory."""

    def __init__(self, directory: Path):
        handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
            *args, directory=str(directory), **kwargs
        )
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://127.0.0.1:{port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _make_zip(zip_path: Path, root_name: str, version: str, decoys: bool = True) -> None:
    """Build a fake zipball with `root_name/` as the single top-level dir."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{root_name}/src/__init__.py", "")
        zf.writestr(f"{root_name}/src/new_mod.py", "NEW_MODULE = True\n")
        zf.writestr(f"{root_name}/system/placeholder.sh", "#!/bin/sh\n")
        zf.writestr(f"{root_name}/utils/placeholder.py", "")
        zf.writestr(f"{root_name}/main.py", "# new main\n")
        zf.writestr(f"{root_name}/requirements.txt", "requests\n")
        zf.writestr(f"{root_name}/.info", f"VERSION='{version}'\n")
        zf.writestr(f"{root_name}/sources.json", "{}")
        if decoys:
            zf.writestr(f"{root_name}/CHANGELOG.md", "# changelog\n")
            zf.writestr(f"{root_name}/NOTES.md", "# notes\n")


class TestIsNewer(unittest.TestCase):
    def test_newer_patch(self):
        self.assertTrue(is_newer("v1.2.2", "v1.2.1"))

    def test_equal(self):
        self.assertFalse(is_newer("v1.2.1", "v1.2.1"))

    def test_no_downgrade(self):
        self.assertFalse(is_newer("v1.2.1", "v1.3.0"))

    def test_non_version_tag_rejected(self):
        self.assertFalse(is_newer("deps-v1", "v1.2.1"))


class TestLatestTag(unittest.TestCase):
    def setUp(self):
        self.assets_dir = Path(tempfile.mkdtemp())
        self.server = _FixtureServer(self.assets_dir)
        self.server.start()
        self.workspace = Path(tempfile.mkdtemp())
        self._old_log_file = config.token_log_file
        config.token_log_file = self.workspace / "github_api_log.json"

    def tearDown(self):
        config.token_log_file = self._old_log_file
        self.server.stop()
        shutil.rmtree(self.assets_dir, ignore_errors=True)
        shutil.rmtree(self.workspace, ignore_errors=True)

    def _write_release(self, tag: str) -> None:
        (self.assets_dir / "releases").mkdir(exist_ok=True)
        (self.assets_dir / "releases" / "latest").write_text(
            f'{{"tag_name": "{tag}"}}', encoding="utf-8"
        )

    def test_valid_tag(self):
        self._write_release("v9.9.9")
        with patch("src.self_update.API_LATEST_URL", f"{self.server.base_url}/releases/latest"):
            updater = SelfUpdater(self.workspace)
            self.assertEqual(updater.latest_tag(), "v9.9.9")

    def test_non_version_tag_returns_none(self):
        self._write_release("deps-v1")
        with patch("src.self_update.API_LATEST_URL", f"{self.server.base_url}/releases/latest"):
            updater = SelfUpdater(self.workspace)
            self.assertIsNone(updater.latest_tag())

    def test_unreachable_server_returns_none(self):
        self.server.stop()
        with patch("src.self_update.API_LATEST_URL", f"{self.server.base_url}/releases/latest"):
            updater = SelfUpdater(self.workspace)
            self.assertIsNone(updater.latest_tag())


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.assets_dir = Path(tempfile.mkdtemp())
        self.server = _FixtureServer(self.assets_dir)
        self.server.start()
        self.workspace = Path(tempfile.mkdtemp())
        (self.workspace / ".info").write_text("VERSION='v1.2.1'\n", encoding="utf-8")
        self._old_log_file = config.token_log_file
        config.token_log_file = self.workspace / "github_api_log.json"

    def tearDown(self):
        config.token_log_file = self._old_log_file
        self.server.stop()
        shutil.rmtree(self.assets_dir, ignore_errors=True)
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_same_version_returns_none(self):
        (self.assets_dir / "releases").mkdir(exist_ok=True)
        (self.assets_dir / "releases" / "latest").write_text(
            '{"tag_name": "v1.2.1"}', encoding="utf-8"
        )
        with patch("src.self_update.API_LATEST_URL", f"{self.server.base_url}/releases/latest"):
            updater = SelfUpdater(self.workspace)
            self.assertIsNone(updater.check())


class TestApply(unittest.TestCase):
    def setUp(self):
        self.assets_dir = Path(tempfile.mkdtemp())
        self.server = _FixtureServer(self.assets_dir)
        self.server.start()
        self.workspace = Path(tempfile.mkdtemp())

        # Pre-seed workspace: old runtime + user state.
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "old_mod.py").write_text("OLD = True\n", encoding="utf-8")
        (self.workspace / "bin").mkdir()
        (self.workspace / "bin" / "aapt2").write_bytes(b"real-aapt2-binary")
        (self.workspace / ".config").write_text("SOURCE='Anddea'\n", encoding="utf-8")
        (self.workspace / "github_token.json").write_text('{"token": "secret"}', encoding="utf-8")
        (self.workspace / ".info").write_text("VERSION='v1.2.1'\n", encoding="utf-8")

        self._old_log_file = config.token_log_file
        config.token_log_file = self.workspace / "github_api_log.json"

    def tearDown(self):
        config.token_log_file = self._old_log_file
        self.server.stop()
        shutil.rmtree(self.assets_dir, ignore_errors=True)
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_apply_replaces_runtime_and_preserves_user_state(self):
        zip_path = self.assets_dir / "v9.9.9.zip"
        _make_zip(zip_path, "Enhancipy-9.9.9", "v9.9.9")

        with patch(
            "src.self_update.ZIP_URL_TEMPLATE",
            f"{self.server.base_url}/{{tag}}.zip",
        ):
            updater = SelfUpdater(self.workspace)
            ok = updater.apply("v9.9.9")

        self.assertTrue(ok)

        # Runtime replaced.
        self.assertFalse((self.workspace / "src" / "old_mod.py").exists())
        self.assertTrue((self.workspace / "src" / "new_mod.py").exists())
        self.assertTrue((self.workspace / "system" / "placeholder.sh").exists())
        self.assertTrue((self.workspace / "utils" / "placeholder.py").exists())
        self.assertEqual(
            (self.workspace / "main.py").read_text(encoding="utf-8"), "# new main\n"
        )
        self.assertEqual(
            (self.workspace / ".info").read_text(encoding="utf-8"), "VERSION='v9.9.9'\n"
        )
        self.assertEqual(
            (self.workspace / "sources.json").read_text(encoding="utf-8"), "{}"
        )

        # User state / dev-only files untouched or absent.
        self.assertEqual(
            (self.workspace / "bin" / "aapt2").read_bytes(), b"real-aapt2-binary"
        )
        self.assertEqual(
            (self.workspace / ".config").read_text(encoding="utf-8"), "SOURCE='Anddea'\n"
        )
        self.assertEqual(
            (self.workspace / "github_token.json").read_text(encoding="utf-8"),
            '{"token": "secret"}',
        )
        self.assertFalse((self.workspace / "CHANGELOG.md").exists())
        self.assertFalse((self.workspace / "NOTES.md").exists())

        # No leftover backup dirs.
        leftovers = list(self.workspace.glob("*.old-*"))
        self.assertEqual(leftovers, [])

    def test_apply_rejects_version_mismatch_and_leaves_workspace_untouched(self):
        zip_path = self.assets_dir / "v9.9.9.zip"
        # Payload's own .info claims a different version than the tag we ask for.
        _make_zip(zip_path, "Enhancipy-9.9.9", "v8.0.0")

        with patch(
            "src.self_update.ZIP_URL_TEMPLATE",
            f"{self.server.base_url}/{{tag}}.zip",
        ):
            updater = SelfUpdater(self.workspace)
            ok = updater.apply("v9.9.9")

        self.assertFalse(ok)
        # Original tree untouched.
        self.assertTrue((self.workspace / "src" / "old_mod.py").exists())
        self.assertEqual(
            (self.workspace / ".info").read_text(encoding="utf-8"), "VERSION='v1.2.1'\n"
        )


class TestRunGating(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp())
        (self.workspace / ".info").write_text("VERSION='v1.2.1'\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_disabled_toggle_skips_network(self):
        with patch.object(config, "is_on", return_value=False), \
             patch("requests.get", side_effect=AssertionError("must not call network")):
            updater = SelfUpdater(self.workspace)
            self.assertEqual(updater.run(), "disabled")


if __name__ == "__main__":
    unittest.main()
