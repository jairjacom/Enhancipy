"""EnhanciPy runtime dependency bootstrap (bin/aapt2, bin/APKEditor.jar).

Mirrors bin/aapt2 and bin/APKEditor.jar from a jairjacom/Enhancipy release
instead of fetching them lazily from third-party repositories. Both files
are gitignored and never committed, so a fresh clone starts with an empty
bin/ directory that this module populates on first run (see
src/tui/screens/boot_screen.py) or on demand (Configure ▸ Runtime
Dependencies, see src/tui/screens/settings.py).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from src.environment import env
from src.utils import DownloadResult, download_file_ex

DEPS_RELEASE_BASE = "https://github.com/jairjacom/Enhancipy/releases/download/deps-v1"
APKEDITOR_ASSET = "APKEditor.jar"
AAPT2_ASSETS = {
    "arm64-v8a": "aapt2-arm64-v8a",
    "armeabi-v7a": "aapt2-armeabi-v7a",
    "x86_64": "aapt2-x86_64",
    "x86": "aapt2-x86",
}


@dataclass
class DepStatus:
    key: str  # "aapt2" | "apkeditor"
    label: str  # "aapt2" | "APKEditor.jar"
    path: Path
    present: bool
    url: Optional[str]  # None when this arch has no mirrored asset


class DependencyBootstrap:
    """Owns the bin/ runtime dependency lifecycle (status + download)."""

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        self.workspace_dir = workspace_dir or Path(__file__).resolve().parent.parent
        self.bin_dir = self.workspace_dir / "bin"
        self.aapt2_bin = self.bin_dir / "aapt2"
        self.apkeditor_jar = self.bin_dir / "APKEditor.jar"

    def aapt2_url(self) -> Optional[str]:
        """Download URL for the arch-matched aapt2 binary, or None if this
        architecture has no mirrored build."""
        arch = env.get_arch()
        asset = AAPT2_ASSETS.get(arch)
        if not asset:
            return None
        return f"{DEPS_RELEASE_BASE}/{asset}"

    def apkeditor_url(self) -> str:
        return f"{DEPS_RELEASE_BASE}/{APKEDITOR_ASSET}"

    def statuses(self) -> List[DepStatus]:
        return [
            DepStatus(
                key="aapt2",
                label="aapt2",
                path=self.aapt2_bin,
                present=self.aapt2_bin.exists(),
                url=self.aapt2_url(),
            ),
            DepStatus(
                key="apkeditor",
                label="APKEditor.jar",
                path=self.apkeditor_jar,
                present=self.apkeditor_jar.exists(),
                url=self.apkeditor_url(),
            ),
        ]

    def missing(self) -> List[DepStatus]:
        return [status for status in self.statuses() if not status.present]

    def ensure(
        self,
        only: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[bool, str]:
        """Download every missing dependency (optionally filtered by `only`
        keys). Never raises. Returns (all_ok, newline-joined summary)."""
        targets = self.missing()
        if only is not None:
            targets = [status for status in targets if status.key in only]

        if not targets:
            return True, "All runtime dependencies are present."

        records: List[str] = []
        all_ok = True

        for status in targets:
            try:
                if status.url is None:
                    records.append(f"{status.label}: no mirrored build for {env.get_arch()}")
                    all_ok = False
                    continue

                self.bin_dir.mkdir(parents=True, exist_ok=True)

                def cb(current: int, total: int, _pct: str, _label: str = status.label) -> None:
                    if progress_callback:
                        progress_callback(_label, current, total)

                result = download_file_ex(status.url, status.path, 0, cb, None, cancel_event)

                if result == DownloadResult.CANCELLED:
                    status.path.unlink(missing_ok=True)
                    records.append(f"{status.label}: cancelled")
                    all_ok = False
                    break

                if result == DownloadResult.OK and status.path.exists():
                    if status.key == "aapt2":
                        status.path.chmod(0o755)
                    records.append(f"{status.label}: downloaded")
                    continue

                status.path.unlink(missing_ok=True)
                records.append(f"{status.label}: download failed")
                all_ok = False
            except Exception:
                status.path.unlink(missing_ok=True)
                records.append(f"{status.label}: download failed")
                all_ok = False

        return all_ok, "\n".join(records)


deps = DependencyBootstrap()
