"""Guard: .info version must match the newest CHANGELOG.md release."""


import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _info_version() -> str:
    text = (ROOT / ".info").read_text(encoding="utf-8")
    match = re.search(r"VERSION\s*=\s*['\"]?([^'\"\n]+)", text)
    assert match, ".info has no VERSION= line"
    return match.group(1).strip()


def _newest_changelog_version() -> str:
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            match = re.search(r"## \[(v[0-9][^\]]*)\]", line)
            if match:
                return match.group(1)
    raise AssertionError("CHANGELOG.md has no '## [vX.Y.Z]' heading")


def test_info_version_matches_changelog():
    assert _info_version() == _newest_changelog_version()
