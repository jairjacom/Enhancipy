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
- Added (this session): scrollbar arrow decoration (▲▼ vertical, ◀▶
  horizontal). New `src/tui/scrollbar.py` (`ArrowScrollBarRender`, a
  `ScrollBarRender` subclass) is installed app-wide via
  `ScrollBar.renderer = ArrowScrollBarRender` in `src/tui/app.py` (the
  documented Textual hook — every scrollbar in every screen renders
  through this one class attribute). Arrow glyphs reuse `bar_color`/
  `back_color`, which Textual already resolves from the
  `scrollbar-color`/`scrollbar-color-hover` CSS tokens
  (`$enh-accent`/`$enh-accent-2` on `ContentContainer`,
  `src/tui/styles.tcss:144-147`) — no per-theme edits needed, hover
  recolor works unchanged. Arrows are suppressed when there's no
  overflow or the track is under 3 cells (`ArrowScrollBarRender.MIN_SIZE`)
  to avoid crowding out the thumb on tiny scrollbars. New
  `tests/test_scrollbar_arrows.py` (5 tests): direct `render_bar` unit
  tests for vertical/horizontal glyph placement + meta
  (`@mouse.down: scroll_up`/`scroll_down`, matching stock end-of-track
  click behavior) and short-bar/no-overflow suppression, plus an
  end-to-end test asserting `ScrollBar.renderer` is installed and ▲▼
  appear in a real `app.export_screenshot()`. Note: a scrollable
  container's on-screen `region.height` can equal `virtual_size.height`
  while still showing a scrollbar (padding eats into the actual content
  track) — use `show_vertical_scrollbar` as the overflow precondition in
  tests, not a height comparison. Full suite: 108/108 passing.
- Fixed (this session): Rish install flow used the **source** app's
  package name for every post-move step, but patch sets (observed:
  Anddea's "Post-processing package name change" step on YouTube
  21.13.164) can rename the package inside the APK. Root-caused live on
  device (SDK 37, `~/EnhanciPy`):
  - Before: `aapt2 dump badging apps/YouTube/21.13.164-Anddea.apk` →
    `package: name='anddea.youtube'`, but `install_or_export`'s rish
    branch called `_run_rish_script`/`run_dex_optimization`/the
    `LAUNCH_APP_AFTER_MOUNT` launch/the downgrade-retry uninstall with
    `com.google.android.youtube` (the *source* app's package) the whole
    way through. The APK actually installed fine as `anddea.youtube`
    (`pm list packages`, `lastUpdateTime` bumped) alongside the untouched
    stock `com.google.android.youtube` 21.37.42 — "installed app is a
    lower version" was the patched 21.13.164 vs. stock 21.37.42, not a
    failed install. Dex optimization and the post-install launch silently
    ran against the **stock** app instead: `dumpsys package
    anddea.youtube` showed `[status=speed-profile] [reason=ab-ota-sync]`
    (background default, nothing we compiled) before the fix.
  - Also found: `system/rish-install.sh`'s `rish()` wrapper discarded
    stderr on the direct (non-temp-file) path, and some probes return
    their result **only on stderr** — reproduced live: `rish -c "getprop
    ro.build.version.sdk"` gave `out='' err='37'` through
    `src/utils.run_rish`. This silently zeroed `DEVICE_SDK` (`Device SDK:
    0`), which silently dropped the user's `BYPASS_LOW_TARGET_SDK_BLOCK`
    flag on an SDK 37 device that needed it. Exact-string probe
    comparisons (`== "Installed"`) also had no tolerance for extra output
    lines.
  - Fix: `rish()` now merges stderr into the piped stdout stream
    (`command rish "$@" 2>&1 | sed ...`) instead of a mktemp dance that
    only forwarded it after the fact; every probe site normalizes/matches
    with `grep -qx` instead of `==`. `src/installer.py` gained
    `AppInstaller._patched_pkg_name()` (`aapt2 dump badging`, presence-only
    — never triggers a network `ensure()`), whose result (falling back to
    the source package name when aapt2 is unavailable/unparseable) is now
    threaded through `_run_rish_script`, `_finish_rish_install` (dexopt +
    launch), `_rish_failure_result`, and — via a new `InstallResult
    .pkg_name` field stashed into the TUI's `_install_ctx` — the
    downgrade-conflict uninstall/reinstall retry. The result message now
    tells the user when a patch renamed the package.
  - Verified end-to-end live on device: ran the real
    `system/rish-install.sh` directly with `anddea.youtube` as `$1` — log
    shows `Device SDK: 37` (previously `0`) and `Existing installation
    detected (v21.13.164) - this will be an UPDATE`. Then ran
    `app_installer.run_dex_optimization('anddea.youtube', 'update')` →
    `(True, 'DEX optimized (speed)')`; `dumpsys package anddea.youtube`
    confirmed `[status=speed] [reason=cmdline]` on the base APK (dexopt
    had never applied to the patched app before this fix). Stock
    `com.google.android.youtube` (21.37.42) confirmed untouched
    throughout. Full suite: 130/130 passing (12 new/updated cases in
    `tests/test_rish_script.py` covering stderr-only probe output and
    `grep -qx` noise tolerance; new `TestPatchedPkgName` +
    renamed-package routing cases in `tests/test_installer.py`).
- Added (this session): uniform auto-height window chrome across every
  screen. New `src/tui/screens/base.py` (`BaseScreen`) composes
  `CyberHeader → ContentContainer("container-box") → Footer` once; every
  screen (except `boot_screen.py`, which has no window chrome, and the
  `ModalScreen` dialogs in `src/tui/widgets/dialogs.py`, already uniform via
  `.dialog-box`) now subclasses it and implements `compose_content()`
  instead of repeating the boilerplate. `main_menu_screen` opts into the
  extra `CyberStatusBar` via `SHOW_STATUS_BAR = True`; `FilePickerScreen`
  (pushed as an instance, not registered in `App.SCREENS`) also migrated.
  `src/tui/styles.tcss` list/scroll caps (`.list-card ListView`,
  `.desc-scroll`, `.toggle-scroll`, `.select-scroll`) converted from fixed
  row counts to `max-height: 60vh`, so lists grow when the Termux on-screen
  keyboard hides (more terminal rows) and shrink when it shows — verified
  live with `pilot.resize_terminal()` in `run_test()`, no keyboard-detection
  code needed since Termux already resizes the pty and Textual's `vh` units
  re-resolve on resize.
  - **Textual 8.2.8 layout quirk found while verifying this**: a
    percentage `max-height` (`max-height: 100%`) on an `auto`-height
    container whose own parent has collapsed to a very small resolved size
    (here: `.list-card`/`.detail-card` inside `ContentContainer` on a
    ~13-row-or-shorter terminal, once header+footer+card chrome eats
    nearly the whole viewport) stops being enforced at all — the
    container's `min-height` is also silently ignored, and a descendant's
    *own* unrelated `max-height: 60vh` cap gets bypassed too, so a 20-item
    `ListView` rendered at its full ~40-row content height instead of
    being capped. Reproduced in isolation (synthetic `BaseScreen` with a
    fake `ListView`) and confirmed the exact break point: terminal height
    14 → capped correctly, 13 → fully uncapped. Fixed by changing
    `.list-card`/`.detail-card` `max-height` from `100%` to `100vh`
    (viewport-relative, same unit family as the children's own caps,
    never collapses toward zero the same way) — re-verified capped
    correctly down to a 10-row terminal.
  - Also hit the **`height: 1fr` sibling-starvation case** this repo's own
    CSS already warns about elsewhere (`settings.py:70-71` comment): giving
    `patch_progress_screen`'s log card `height: 1fr` to "fill remaining
    space" let the *first* card (status + buttons, `height: auto`) eat
    nearly the whole `ContentContainer` on short terminals, starving the
    log card to 0 rows. Fixed by keeping `.log-card` at `height: auto` and
    giving `#log-viewer` itself a direct `height: 60vh` (not `auto` +
    `max-height`, which only grows with content — an empty log starts at
    its `min-height` floor and never fills available space) so the log
    viewer always occupies a viewport-relative slice regardless of content.
  - `tests/test_layout_reach.py::test_theme_list_fits_viewport` pinned the
    old "`.list-card` never needs scrolling" invariant from before this
    change; that invariant is now intentionally relaxed (lists can need
    scrolling to reach content below them, by design, once they grow
    toward the 60vh cap), so the test was deleted — superseded by
    `tests/test_base_screen.py::test_list_auto_adjusts_to_viewport`, which
    pins the new cap directly (`FilePickerScreen` at 80×24 → list height
    14; resized to 80×10 → list height 6).
  - New `tests/test_base_screen.py`: `test_every_screen_uses_base_window`
    (every `App.SCREENS` entry except `boot_screen`, plus
    `FilePickerScreen`, subclasses `BaseScreen`) and
    `test_list_auto_adjusts_to_viewport` (pinned resize numbers above).
  - Verified: full programmatic walk of every registered screen at 80×24
    and 80×12 (`CyberHeader` + `ContentContainer` + `Footer` all present,
    no crashes); `patch_progress_screen`'s log viewer measured at 26/10/3
    content rows for 50/24/12-row terminals. **Not yet verified live on a
    physical device** — this is Textual layout/CSS only, no rish/install
    changes, so the AGENTS.md device-verification requirement doesn't
    apply, but a real-device keyboard-show/hide check is still recommended
    before trusting pixel-perfect behavior outside the test harness. Full
    suite: 138/138 passing.

