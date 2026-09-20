"""
Runtime dependency bootstrap regression tests (src/deps.py).

bin/aapt2 and bin/APKEditor.jar are gitignored and never committed, so a
fresh clone starts with an empty bin/ directory. `DependencyBootstrap.ensure`
must populate it from the project's own release assets and must not damage
the target directory when the current architecture has no mirrored build.

Uses a local HTTP server instead of the real GitHub release so this test
never depends on network access or on the release actually existing yet.
"""

from __future__ import annotations

import http.server
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src.deps import DependencyBootstrap


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


class TestDependencyBootstrap(unittest.TestCase):
    def setUp(self):
        self.assets_dir = Path(tempfile.mkdtemp())
        (self.assets_dir / "APKEditor.jar").write_bytes(b"fake-apkeditor-bytes")
        (self.assets_dir / "aapt2-arm64-v8a").write_bytes(b"fake-aapt2-bytes")

        self.server = _FixtureServer(self.assets_dir)
        self.server.start()

        self.workspace = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.server.stop()
        shutil.rmtree(self.assets_dir, ignore_errors=True)
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_downloads_missing_deps_for_supported_arch(self):
        with patch("src.deps.DEPS_RELEASE_BASE", self.server.base_url), \
             patch("src.deps.env.get_arch", return_value="arm64-v8a"), \
             patch("src.utils.config.is_on", return_value=True):
            bootstrap = DependencyBootstrap(self.workspace)
            ok, summary = bootstrap.ensure()

        self.assertTrue(ok, summary)
        aapt2 = self.workspace / "bin" / "aapt2"
        apkeditor = self.workspace / "bin" / "APKEditor.jar"
        self.assertTrue(aapt2.exists())
        self.assertTrue(apkeditor.exists())
        self.assertEqual(aapt2.read_bytes(), b"fake-aapt2-bytes")
        self.assertEqual(apkeditor.read_bytes(), b"fake-apkeditor-bytes")
        self.assertEqual(oct(aapt2.stat().st_mode)[-3:], "755")

    def test_unsupported_arch_reports_failure_without_writing(self):
        with patch("src.deps.DEPS_RELEASE_BASE", self.server.base_url), \
             patch("src.deps.env.get_arch", return_value="mips"), \
             patch("src.utils.config.is_on", return_value=True):
            bootstrap = DependencyBootstrap(self.workspace)
            ok, summary = bootstrap.ensure(only=["aapt2"])

        self.assertFalse(ok)
        self.assertIn("no mirrored build for mips", summary)
        self.assertFalse((self.workspace / "bin" / "aapt2").exists())


if __name__ == "__main__":
    unittest.main()
