# EnhanciPy — Working Notes

Engineering log for continuity across sessions. Not user-facing (see
`README.md` for install/usage, `CHANGELOG.md` for release notes). Append to
this file as work happens; don't let findings live only in chat history.

## Project story (from git log, 2026-09-20)

Repo has 6 commits total, all authored `jairjacom`, all dated 2026-09-20,
pushed to `origin/main` (`github.com/jairjacom/Enhancipy`). No earlier
history exists in this tree (checked `git log --all`, full reflog, and
grepped for any prior working-dir name — none found).

1. `ef90c11` — **Enhancify Python TUI: standalone tree without the bash UI.**
   Initial commit, lands the full rewrite in one shot (62 files, ~14.5k
   lines) — extracted from the upstream bash/`dialog` Enhancify (itself a
   fork of Revancify, based on Enhancify v6.2.6 / jair-00's mod), not built
   up incrementally in this history.
2. `05c256d` — **theme: single-source token palette drives all chrome.**
   `ThemeInfo` replaced ad-hoc primary/secondary/bg/css_class fields with a
   14-value token set + `palette()`/`css_variables()` accessors. Deleted 662
   lines of duplicated per-theme CSS blocks (352 hex literals). Fixed
   list-card scroll overflow (cards were sized `height:100%` and pushed
   off-screen).
3. `e996803` — **theme+brand: tokenize remaining colors, scrollable detail
   cards, EnhanciPy wording pass.** Every remaining hardcoded Textual/Rich
   color literal moved to `$enh-*` tokens or `palette()` lookups (resolved
   at render time, not frozen at import). 5 detail/changelog cards converted
   to `VerticalScroll` for keyboard-nav reachability. Visible strings only
   rebranded to EnhanciPy / jair-00 credit — every code identifier, path,
   env var, config key, GitHub repo slug, User-Agent, keystore alias left
   untouched.
4. `3bb1766` — **tests: pin theme-switch recolor, list scroll fit/wrap.**
   Regression tests for the above two commits' behavior.
5. `bc77f92` — **v1.0.0: in-app EnhanciPy branding, own changelog,
   dependency bootstrap.** New `src/deps.py` (`DependencyBootstrap`) owns
   `bin/aapt2` + `bin/APKEditor.jar` status/download against this project's
   own `deps-v1` GitHub release, replacing lazy third-party fetches that
   silently failed mid-patch. Boot screen runs it on first launch (gated by
   `ENHANCIPY_DEP_BOOTSTRAP`), Settings gained manual re-fetch. Version
   bumped to v1.0.0.
6. `fe73be0` (HEAD) — **fix: rish-install.sh reading wrong .config path.**
   `system/rish-install.sh:43` hardcoded `CONFIG_FILE="$HOME/Enhancify/.config"`
   (stale path from the upstream Enhancify fork) instead of this project's
   `EnhanciPy` workspace, so the script always fell through to defaults —
   `BYPASS_LOW_TARGET_SDK_BLOCK`/`SKIP_VERIFICATION` from the user's real
   `.config` were silently ignored on Rish installs. Fixed by resolving
   `CONFIG_FILE` via a `ENHANCIFY_CONFIG_FILE` env override with a
   script-relative `$SCRIPT_DIR/../.config` fallback (no hardcoded
   directory name); `run_command()` (`src/utils.py`) gained an `env`
   kwarg merged over `os.environ`; `installer.py`'s Rish call site now
   passes `ENHANCIFY_CONFIG_FILE=config.config_file` so the shell script
   always agrees with the Python `ConfigManager`'s actual workspace.
   Verified end-to-end with a stubbed `rish` binary (fallback path and
   env-override path both resolve/parse correctly); no version bump —
   no tag/release convention exists in this repo yet.

## Current verified state (as of 2026-09-20 session)

- **Tests**: 67/67 passing (`python -m pytest tests -q`, run from repo
  root — tests import `src.*`). One benign `RuntimeWarning` (unawaited
  Textual timer coroutine in `src/tui/widgets/switch.py:137`), not a
  failure.
- **No stub/TODO markers** in `src/` — grepped for
  `TODO|FIXME|NotImplementedError|stub|placeholder`; only hits are
  legitimate `Input(placeholder=...)` UI kwargs.
- **Not yet done**: no end-to-end run against a real device / real APK
  patch — test suite is unit/widget level only. No CI config
  (`.github/workflows`) exists; tests are manual-run only.

## Key behavioral facts (don't re-derive these)

- **Java version support**: `Environment.detect_java_version()`
  (`src/environment.py:244`) explicitly detects 17, 21, and 25
  (`openjdk 25` etc.), and `patcher.py:164` accepts "OpenJDK 17/21/25".
  README's `pkg install python openjdk-17 aria2` is just the documented
  default — any of 17/21/25 works, whichever `java` is on `PATH`.
  Unrecognized versions fall back to an "other" label (cosmetic only, not
  a functional gate).
- **Runtime deps download once, not per-update**: `bin/aapt2` and
  `bin/APKEditor.jar` are gitignored, never committed. `DependencyBootstrap
  .ensure()` (`src/deps.py`) checks file **presence** only — no version or
  checksum comparison. Fresh clone → `bin/` empty → boot screen fetches
  both from the `deps-v1` release once. `git pull` on an existing checkout
  → files already present → `ensure()` skips, even if a newer `deps-v1`
  release exists. Re-fetch requires deleting `bin/*` or using Settings ▸
  Configure ▸ Runtime Dependencies.
- **Install sequence for a new user** (README already has this, just
  missing an explicit `git clone` step):
  ```
  pkg install git python openjdk-17 aria2   # or openjdk-21 / openjdk-25
  git clone https://github.com/jairjacom/Enhancipy.git
  cd Enhancipy
  pip install -r requirements.txt
  python main.py
  ```

## Open items / next session

- Fixed this session: Rish-mode installs silently ignored the user's
  `.config` (see commit 6 above).
- Fixed (this session, follow-up): Rish detection/install path was
  fundamentally broken despite passing tests, root-caused via live device
  probing (SDK 37 device, `~/EnhanciPy`):
  - `check_privileges()`'s rish probe used `timeout=1` against a measured
    ~1.0s `rish -c` round trip → `TimeoutExpired` → false `Non-privilege
    Mode` → every install fell through to the `termux-open` export branch,
    never touching `rish-install.sh` or dexopt.
  - `rish` **always exits 0** regardless of the inner command's outcome
    (`rish -c "exit 7"` → rc 0). Every `code != 0` check on a rish command
    was dead code (`run_dex_optimization`, the install-script exit code).
    Real failures are text-only, sometimes split across stdout/stderr, and
    always prefixed with an `Entering shell...` banner.
  - `rish` silently no-ops (rc 0, empty output) when `RISH_APPLICATION_ID`
    is unset — it defaults to the literal string `"PKG"`. Any non-login
    shell/process without that var exported reproduces total silent
    failure.
  - Fix: `src/utils.py` gained `run_rish`/`rish_available`/`rish_environ`/
    `strip_rish_banner` — rish detection is now marker-based
    (`echo ENH_RISH_OK` round trip, not returncode), `RISH_APPLICATION_ID`/
    `MANAGER_APPLICATION_ID` are defaulted when unset, and all rish output
    consumers read text, not exit codes. `run_dex_optimization` now returns
    `(bool, str)` and verifies the applied compiler filter via `dumpsys`
    with a `quicken → speed` fallback and an "unverified" escape hatch for
    unfamiliar `dumpsys` formats. `system/rish-install.sh` gates
    `--skip-verification`/`--bypass-low-target-sdk-block` on `getprop
    ro.build.version.sdk >= 34` and retries once without them if `pm`
    rejects the flags. Stale `install_type.txt`/`rish_log.txt`/
    `install_error.txt` are now cleared before every rish install attempt.
  - New `tests/test_rish_script.py` exercises the actual shell script
    (not a Python re-implementation) against a stub `rish` binary
    impersonating SDK 33/34/36 — the only coverage for Android versions
    other than the one physical device available this session.
  - Verified live on-device: `check_privileges(refresh=True)` now returns
    `(False, True, 'Rish Mode')` (previously `Non-privilege Mode`);
    `rish_available()` correctly returns `False` under
    `RISH_APPLICATION_ID=PKG` (the silent-no-op signature);
    `run_dex_optimization('com.does.not.exist')` correctly returns
    `(False, 'Error: Package not found: ...')`. Full suite: 91/91 passing.
