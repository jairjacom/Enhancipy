#!/usr/bin/env python3
"""Regenerate the feature and requirements sections of README.md.

Source of truth: docs/features.json. Only the text between
<!-- FEATURES:START --> / <!-- FEATURES:END --> and
<!-- REQUIREMENTS:START --> / <!-- REQUIREMENTS:END --> is rewritten.
Everything else in README.md is hand-written and left alone.

Usage:
    python tools/gen_readme.py           # rewrite README.md
    python tools/gen_readme.py --check   # exit 1 if README.md is out of date
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "docs" / "features.json"
README_PATH = ROOT / "README.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"

MARKER_RE = {
    name: re.compile(
        rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.DOTALL
    )
    for name in ("FEATURES", "REQUIREMENTS")
}


def load_data(path: Path = DATA_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: dict) -> None:
    """Fail loudly on dangling references so the README cannot drift."""
    categories = {c["id"] for c in data["categories"]}
    requirements = {r["id"]: r for r in data["requirements"]}
    ids = set()
    for feature in data["features"]:
        if feature["id"] in ids:
            raise ValueError(f"duplicate feature id: {feature['id']}")
        ids.add(feature["id"])
        if feature["category"] not in categories:
            raise ValueError(
                f"{feature['id']}: unknown category {feature['category']!r}"
            )
        for req in feature["requires"]:
            if req not in requirements:
                raise ValueError(f"{feature['id']}: unknown requirement {req!r}")
        if not re.fullmatch(r"v\d+\.\d+\.\d+", feature["since"]):
            raise ValueError(f"{feature['id']}: since must look like vX.Y.Z")


def released_versions(changelog: Path = CHANGELOG_PATH) -> set:
    text = changelog.read_text(encoding="utf-8")
    return set(re.findall(r"^## \[(v\d+\.\d+\.\d+)\]", text, re.M))


def render_features(data: dict) -> str:
    titles = {r["id"]: r["title"] for r in data["requirements"]}
    lines = []
    for category in data["categories"]:
        items = [f for f in data["features"] if f["category"] == category["id"]]
        if not items:
            continue
        lines.append(f"### {category['title']}")
        lines.append("")
        lines.append("| Feature | What it does | Needs | Since |")
        lines.append("| --- | --- | --- | --- |")
        for f in items:
            needs = ", ".join(titles[r] for r in f["requires"]) or "Nothing extra"
            lines.append(
                f"| **{f['title']}** | {f['summary']} | {needs} | {f['since']} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_requirements(data: dict) -> str:
    lines = [
        "| Permission or tool | Needed for | How to set it up |",
        "| --- | --- | --- |",
    ]
    for r in data["requirements"]:
        needed = "Optional" if r["optional"] else "Required"
        lines.append(f"| **{r['title']}** | {needed} | {r['how']} |")
    return "\n".join(lines) + "\n"


def render(readme_text: str, data: dict) -> str:
    bodies = {
        "FEATURES": "\n" + render_features(data),
        "REQUIREMENTS": "\n" + render_requirements(data),
    }
    out = readme_text
    for name, body in bodies.items():
        match = MARKER_RE[name].search(out)
        if not match:
            raise SystemExit(f"README.md is missing the {name} markers")
        out = out[: match.start(2)] + body + out[match.end(2):]
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if README.md is stale")
    args = parser.parse_args(argv)

    data = load_data()
    unknown = sorted({f["since"] for f in data["features"]} - released_versions())
    if unknown:
        print(f"since versions not in CHANGELOG.md: {', '.join(unknown)}", file=sys.stderr)
        return 1

    current = README_PATH.read_text(encoding="utf-8")
    updated = render(current, data)
    if args.check:
        if updated != current:
            print("README.md is out of date: run python tools/gen_readme.py", file=sys.stderr)
            return 1
        return 0
    if updated != current:
        README_PATH.write_text(updated, encoding="utf-8")
        print("README.md updated")
    else:
        print("README.md already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
