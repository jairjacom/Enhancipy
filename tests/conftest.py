import os
from pathlib import Path

import pytest

os.environ.setdefault("ENHANCIPY_DEP_BOOTSTRAP", "0")
os.environ.setdefault("ENHANCIFY_BOOT_SECONDS", "0.01")

REPO_CONFIG = Path(__file__).resolve().parent.parent / ".config"


@pytest.fixture(autouse=True, scope="session")
def isolate_user_config(tmp_path_factory):
    """Point the src.config singleton at a throwaway .config for the whole run.

    src.config.config is a module-level singleton whose config_file is the
    repo-root .config — the user's live settings. Tests call config.set() and
    set_current_theme() on it (tests/test_enhancify.py::test_theme_manager
    resets THEME_ID to cyber_green), so an unisolated run silently reverts the
    user's chosen theme and toggles.
    """
    from src.config import config

    sandbox = tmp_path_factory.mktemp("enhancipy-config")
    original_file = config.config_file
    original_settings = dict(config.settings)

    config.config_file = sandbox / ".config"
    config.load_config()  # file missing -> writes DEFAULT_CONFIG into the sandbox
    try:
        yield config
    finally:
        config.config_file = original_file
        config.settings = original_settings
