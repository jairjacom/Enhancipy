"""README feature sections must be generated from docs/features.json."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("gen_readme", ROOT / "tools" / "gen_readme.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_readme_matches_features_data():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data = gen.load_data()
    assert gen.render(readme, data) == readme, (
        "README.md is stale; run python tools/gen_readme.py"
    )


def test_every_since_version_is_a_released_changelog_entry():
    data = gen.load_data()
    unknown = {f["since"] for f in data["features"]} - gen.released_versions()
    assert not unknown


def test_dangling_requirement_reference_is_rejected():
    data = copy.deepcopy(gen.load_data())
    data["features"][0]["requires"] = ["no-such-requirement"]
    with pytest.raises(ValueError, match="unknown requirement"):
        gen.validate(data)
