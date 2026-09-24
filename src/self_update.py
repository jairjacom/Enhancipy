"""EnhanciPy self-update on launch.

Mirrors the upstream Enhancify launcher's update flow: compare the local
`.info` version against the latest GitHub release of jairjacom/Enhancipy; if
a newer `vX.Y.Z` tag exists, download that tag's source zip and replace only
the Python-TUI runtime (src/, system/, utils/, main.py, requirements.txt,
.info, sources.json). Dev-only files (CHANGELOG.md, NOTES.md, README.md,
AGENTS.md, tests/) and all user state (.config, github_token.json, bin/,
keystore/, ...) are never touched.

This module never calls os.execv — the caller (main.py) owns process
control, which keeps SelfUpdater unit-testable without spawning processes.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Optional

import requests

from src.config import config
from src.utils import DownloadResult, download_file_ex

UPDATE_REPO = "jairjacom/Enhancipy"
API_LATEST_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
ZIP_URL_TEMPLATE = f"https://github.com/{UPDATE_REPO}/archive/refs/tags/{{tag}}.zip"
# Local copy of the GitHub UA — same convention as assets.py, features.py,
# sources.py (each module owns its own USER_AGENT_GITHUB).
USER_AGENT_GITHUB = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36 EdgA/142.0.0.0"

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
INFO_VERSION_RE = re.compile(r"VERSION=['\"]?(v\d+\.\d+\.\d+)['\"]?")

RUNTIME_DIRS = ("src", "system", "utils")
RUNTIME_FILES = ("main.py", "requirements.txt", ".info", "sources.json")


def _parse_tag(tag: str) -> Optional[tuple]:
    match = TAG_RE.match(tag or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(remote: str, local: str) -> bool:
    """True only if `remote` and `local` both parse as vX.Y.Z and remote > local.

    Unparsable tags (e.g. `deps-v1`) or an equal/older remote return False —
    this also blocks accidental downgrade when the local tree is already
    ahead of the "latest" release.
    """
    remote_v = _parse_tag(remote)
    local_v = _parse_tag(local)
    if remote_v is None or local_v is None:
        return False
    return remote_v > local_v


class SelfUpdater:
    """Checks GitHub for a newer EnhanciPy release and applies it in place."""

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        self.workspace_dir = workspace_dir or Path(__file__).resolve().parent.parent
        self.info_file = self.workspace_dir / ".info"

    # --- HTTP ---

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT_GITHUB,
        }
        tok = config.get_github_token()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        return headers

    def _local_version(self) -> str:
        if not self.info_file.exists():
            return ""
        match = INFO_VERSION_RE.search(self.info_file.read_text(encoding="utf-8"))
        return match.group(1) if match else ""

    def latest_tag(self) -> Optional[str]:
        """Latest stable release tag, or None on any network/parse failure."""
        try:
            r = requests.get(API_LATEST_URL, headers=self._headers(), timeout=5)
            limit = int(r.headers.get("x-ratelimit-limit", 0))
            rem = int(r.headers.get("x-ratelimit-remaining", 0))
            reset = int(r.headers.get("x-ratelimit-reset", 0))
            config.log_github_api_call(API_LATEST_URL, limit, rem, reset)

            if r.status_code != 200:
                return None
            tag = r.json().get("tag_name", "")
            return tag if TAG_RE.match(tag) else None
        except Exception:
            return None

    def check(self) -> Optional[str]:
        """Latest tag if it's newer than the local version, else None."""
        latest = self.latest_tag()
        if latest is None:
            return None
        return latest if is_newer(latest, self._local_version()) else None

    # --- Apply ---

    @staticmethod
    def _extracted_root(extract_dir: Path) -> Optional[Path]:
        """The zipball's single top-level directory (name varies by GitHub)."""
        dirs = [p for p in extract_dir.iterdir() if p.is_dir()]
        return dirs[0] if len(dirs) == 1 else None

    @staticmethod
    def _verify_payload(root: Path, tag: str) -> bool:
        for d in RUNTIME_DIRS:
            if not (root / d).is_dir():
                return False
        for f in RUNTIME_FILES:
            if not (root / f).is_file():
                return False
        match = INFO_VERSION_RE.search((root / ".info").read_text(encoding="utf-8"))
        return bool(match) and match.group(1) == tag

    def apply(self, tag: str) -> bool:
        """Download, verify, and install `tag`. False leaves the tree untouched
        (or, in the unlikely case a swap fails mid-way, leaves `.old-<tag>`
        backups behind for manual recovery)."""
        url = ZIP_URL_TEMPLATE.format(tag=tag)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "update.zip"
            if download_file_ex(url, zip_path, headers=self._headers()) != DownloadResult.OK:
                return False

            extract_dir = tmp_path / "extracted"
            extract_dir.mkdir()
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(extract_dir)
            except Exception:
                return False

            root = self._extracted_root(extract_dir)
            if root is None or not self._verify_payload(root, tag):
                return False

            backups = []
            try:
                for d in RUNTIME_DIRS:
                    dest = self.workspace_dir / d
                    backup = self.workspace_dir / f"{d}.old-{tag}"
                    if backup.exists():
                        shutil.rmtree(backup, ignore_errors=True)
                    if dest.exists():
                        dest.rename(backup)
                        backups.append(backup)
                    shutil.move(str(root / d), str(dest))

                for f in RUNTIME_FILES:
                    shutil.copy2(root / f, self.workspace_dir / f)
            except Exception:
                return False

            for backup in backups:
                shutil.rmtree(backup, ignore_errors=True)
            return True

    # --- Dependencies ---

    def _requirements_hash(self) -> str:
        req = self.workspace_dir / "requirements.txt"
        if not req.exists():
            return ""
        return hashlib.sha256(req.read_bytes()).hexdigest()

    def ensure_requirements(self, old_hash: str) -> None:
        """Reinstall requirements.txt only if `apply` actually changed it.

        Non-fatal: a stale dependency beats a broken launch.
        """
        if self._requirements_hash() == old_hash:
            return
        req = self.workspace_dir / "requirements.txt"
        if not req.exists():
            return
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req)],
                timeout=300,
                check=False,
            )
        except Exception as e:
            print(f"[!] Failed to install updated dependencies: {e}")

    # --- Orchestration ---

    def run(self) -> str:
        """One of: "current", "updated", "skipped", "disabled"."""
        if not config.is_on("AUTO_UPDATE"):
            return "disabled"

        print("Checking for updates...")
        tag = self.check()
        if tag is None:
            return "current"

        print(f"Update {tag} available — installing...")
        old_hash = self._requirements_hash()
        if not self.apply(tag):
            print("Update failed — continuing with the current version.")
            return "skipped"

        self.ensure_requirements(old_hash)
        print(f"Updated to {tag}.")
        return "updated"
