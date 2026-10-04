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
- Fixed (this session): every screen froze on open. Root cause:
  `BaseScreen.compose()` ran `env.check_privileges()` (`su -c exit`,
  timeout 5, then the rish probe, timeout 8) and `env.check_network()`
  (two 0.8s socket dials, 30s TTL) synchronously on the UI thread on
  *every* screen mount. `CyberHeader.compose()` additionally spawned
  `java -version` (~0.43s measured) on every mount for a `java_ver`
  result nobody read, plus an uncached `getprop` arch lookup
  (~0.20s). `PatchProgressScreen.action_install` also blocked the UI
  thread with `env.check_privileges(refresh=True)` before the
  "Installing APK" modal could appear.
  - Fix (`src/environment.py`): `check_privileges()`/`check_network()`
    bodies now run under `threading.Lock`s, so concurrent callers
    share one in-flight probe instead of racing su/rish/sockets
    independently; `get_arch()` is memoized (ABI can't change at
    runtime); new `last_privileges()`/`last_network_status()` peek the
    cache without probing. `BaseScreen.compose()`
    (`src/tui/screens/base.py`) now renders the last known values (or
    `"Checking..."`) instantly and `on_mount()` refreshes them via a
    `@work(thread=True)` worker that recomposes
    `CyberHeader`/`CyberStatusBar` and calls a new
    `privileges_resolved()` hook on the UI thread.
    `MainMenuScreen`'s root-only "Unmount Patched App" button is now
    always composed with `display` toggled by that hook instead of
    being conditionally yielded. `BootScreen.on_mount` fires a
    `check_privileges()` pre-warm thread behind the splash so the main
    menu is usually already resolved on arrival (reuses the same probe
    via the step-1 lock, never probes twice). `CyberHeader` no longer
    calls `detect_java_version()`. `PatchProgressScreen.run_install_worker`
    (not `action_install`) now does the `refresh=True` re-probe, inside
    the thread worker, after the "Installing APK" modal is already
    pushed.
  - Timing smoke (`EnhancifyApp().run_test`, this device, SDK 37, Rish
    Mode): boot → main menu 2.887s → 0.481s; Settings push/pop
    ~0.98s → ~0.32s per round trip. Final header badge still resolves
    to the real `⚙️ Rish Mode` once the worker completes.
  - New `tests/test_status_probe.py` (2 tests):
    `test_screen_mounts_before_privilege_probe_and_updates_after` pins
    that the main menu appears in <2s while a gated `check_privileges`
    is still blocked, shows `"Checking..."` and a hidden unmount
    button, then picks up `"Root Mode"` on the header/status bar and
    reveals the button once the gate releases.
    `test_install_press_returns_before_live_reprobe` pins that
    `action_install()` returns in <1s and the "Installing APK" modal
    appears before a gated live re-probe resolves, and that
    `install_or_export` is called with the post-probe
    `(has_root, has_rish)` values. New
    `TestPrivilegeCaching.test_concurrent_callers_share_one_probe`
    (`tests/test_environment.py`) pins the single-flight lock: two
    threads racing `check_privileges()` produce exactly one
    `subprocess.run` call. Confirmed all three fail against pre-fix
    `src/` (`git stash push -- src`): two su calls instead of one, and
    both UI-thread timing assertions exceed their bounds (~5-6s).
  - Verified live on device (`python main.py`, SDK 37, rish-capable,
    non-root): main menu renders real badges with no freeze (`⚙️ Rish
    Mode`, `🌐 Online`, `🤖 arm64-v8a` in both the header and the
    status bar), and `Unmount Patched App` is correctly absent (this
    device has no root). **Not yet verified: the Install button's live
    re-probe on a real patched APK** — that needs an actual patch run
    plus a Rish install, which the user should confirm themselves
    before this merges. Full suite: 141/141 passing.
- Fixed (this session): `SpecsScreen` froze on every open (candidate #1
  above), and a real race surfaced an empty "Asset load failed: " error
  after a patches download, wiping `apps_data` (misdiagnosed in candidate
  #3 above as device-thermal flakiness — it was reproducible 4/6 isolated
  runs on an idle device).
  - Freeze root cause: `SpecsScreen.compose_content` (`specs.py:61`) called
    `env.detect_java_version()` uncached on every open (~0.4-0.6s `java
    -version` spawn on the UI thread, same class of bug just fixed in
    `CyberHeader`). Fix: `detect_java_version(refresh: bool = False)` now
    memoizes like `get_arch()`; `run_patch` (`src/patcher.py`) passes
    `refresh=True` so a mid-session JDK upgrade is still gated correctly;
    `BootScreen.on_mount` gained a pre-warm thread so the cache is usually
    already warm by the first Specs open.
  - Race root cause: `AppSelectScreen.run_parse_worker`
    (`app_select.py:284`) dismisses `parse_modal`, then line 335 called
    `parse_modal.update_message(...)` on the now-detached modal from a
    worker thread. `_ui_call` (`dialogs.py:25`)'s `getattr(screen, "app",
    None)` doesn't catch `RuntimeError` — Textual's `MessagePump.app`
    raises `NoActiveAppError` (a `RuntimeError` subclass) instead of
    returning `None` on a detached screen with no `active_app` contextvar.
    The exception landed in `run_parse_worker`'s `except`, surfacing
    `MessageDialog("Error", "Asset load failed: ")` with an empty reason
    and never setting `apps_data`. Fix: `_ui_call` now does
    `try: app = screen.app / except RuntimeError: return` instead of
    `getattr(..., None)`; the dead post-dismiss `update_message` call at
    `app_select.py:335` was deleted (unreachable — the modal is always
    dismissed one line before `_resolve_apkmirror_names` is invoked).
  - Verified live on this device: 10/10 runs of the formerly-flaky test
    passed (~2.4s each, vs. the pre-fix 4/6-failing baseline at ~18.7s);
    stashing the `dialogs.py` fix reproduces the exact
    `NoActiveAppError` the new regression test
    (`tests/test_download_ui.py::TestUiCallDetached`) pins. Programmatic
    `run_test()` smoke confirmed zero `java -version` subprocess calls on
    either of two consecutive Specs pushes (one from boot pre-warm only),
    and the Specs label correctly reads `Java Runtime : OpenJDK 25`. The
    min-JDK gate's `refresh=True` was confirmed live: a stale cached "17"
    correctly rejects a MorpheApp run with
    `"requires OpenJDK 21+ ... found OpenJDK 17"`, then re-probing to a
    real "21" (same process, same stale cache) passes the gate on the next
    call. Full suite: 143/143 passing.
- Fixed (this session): any patch depending on the Spoof Signature patch
  family (used for license/paywall-bypass patches, e.g. hoo-dles' "Enable
  Niagara Pro") crashed with a raw `app.morphe.util.NoCertificateException:
  Unable to extract certificate from apk` on **every** bundle-distributed
  app (APKM/APKS/XAPK from APKMirror) and on **every** multi-ABI app with
  `OPTIMIZE_LIBS` on (the default) — not an APKMirror or patch-source
  issue, confirmed by diffing a real captured `patch_log.txt` (Niagara
  Launcher, source hoo-dles) against its raw pre-merge `base.apk` split.
  - Root cause: `src/antisplit.py`'s `antisplit_apkm`/`antisplit_apks`/
    `antisplit_xapk` merge split APKs via `APKEditor.jar m`, which can't
    carry a per-split v2/v3 signature over to merged content and produces
    a completely certificate-less APK (verified byte-for-byte: raw
    `base.apk` has an `APK Sig Block 42` magic + `META-INF/CERT.*`; the
    merged output has neither). `optimize_native_libs` independently
    destroys signatures too — it explicitly deletes
    `META-INF/*.SF/.RSA/.DSA/.EC` and rewrites the zip from scratch via
    `zipfile.ZipFile`, which can't preserve the APK Signing Block either —
    and runs by default on every multi-ABI single-APK download, since
    `OPTIMIZE_LIBS` defaults `"on"` (`src/config.py:21`). The patch CLI's
    cert extraction reads straight from the input APK's raw bytes during
    patching, independent of any `--keystore`/`--unsigned` *output*-signing
    flag, and there is no `--original-apk`/signer-source override
    (`patch --help` only has output-signing flags) — so this crashed
    deterministically whenever the input had nothing to extract.
  - Fix: both code paths now call a new `AntiSplitManager._sign_for_patching`
    right after producing their output, which generates an internal
    throwaway PKCS12 keystore (`<storage>/antisplit.keystore`, via
    `keytool`, lazy + cached) and re-signs with the vendored
    `utils/apksigner.jar` (v1+v2+v3, `--min-sdk-version=1` to avoid relying
    on binary-manifest parsing). This is correct, not just
    crash-avoidance: the Spoof Signature patch family extracts *whatever*
    certificate is present at patch time and patches the app's own
    signature-check call sites to always report that embedded value — it
    doesn't matter which key/cert was used, only that one exists. Both
    operations are best-effort (signing failure leaves the pre-existing
    unsigned-output behavior unchanged, never blocks the merge/strip
    result).
  - Verified end-to-end on this device with the real captured failure:
    copied the exact Niagara Launcher merged output that had produced
    `NoCertificateException`, confirmed it had zero signing material,
    signed it with the new helper (confirmed `APK Sig Block 42` +
    `META-INF/MANIFEST.MF` now present), then re-ran the *exact* failing
    CLI command from the captured log against the signed file — it now
    logs `INFO: Applied: Enable Niagara Pro` and writes a complete patched
    output, no exception. New `tests/test_antisplit_signing.py`
    (`TestSignForPatching`, 2 tests) exercises the real vendored
    `apksigner.jar`/`keytool` (not mocked — the contract is "produces an
    actually extractable certificate," which a mocked subprocess can't
    prove) against a throwaway fixture APK, and keystore-caching.
    Confirmed failing pre-fix via `git stash`. Full suite: 145/145
    passing.
- Fixed (this session): Rish-mode installs of any app whose exported
  filename contains a space (any app with a space in its display name —
  the overwhelming majority, e.g. "Niagara Launcher ‧ Home Screen",
  "YouTube Music") failed every time with "Failed to stage APK for
  installation (move to /data/local/tmp failed)" right after a successful
  patch, reported live via `install_error.txt`/`rish_log.txt` from this
  device immediately after the Spoof-Signature fix above let a bundle-app
  patch succeed for the first time.
  - Root cause: `system/rish-install.sh` interpolated
    `$EXPORTED_APP_PATH`/`$PATCHED_APP_PATH` **unquoted** into the string
    handed to `rish -c "..."` (lines that move the exported APK into
    `/data/local/tmp/enhancify` before `pm install`, and move it back on
    failure). `rish -c "<string>"` doesn't run `<string>` in this script's
    own shell — it hands the whole string to the `rish`/Shizuku backend,
    which re-parses it as a brand-new command line on the device side. An
    unquoted path containing a space silently splits into multiple `mv`
    argv words at that second parse, so `mv` either errors or silently
    fails to produce the destination file, and the script's own
    `[ -e $PATCHED_APP_PATH ]` existence check correctly detects the
    failure and surfaces it as the generic staging-error message.
  - Fix: new `shquote()` helper (POSIX single-quote escaping, not
    bash-specific `${var@Q}`/`printf %q`, since rish's backend shell is
    unknown) wraps both paths once after they're built;
    `$EXPORTED_APP_PATH_Q`/`$PATCHED_APP_PATH_Q` replace the unquoted
    variables at both `mv -f` call sites (stage-for-install and
    revert-on-failure). Every other `$PATCHED_APP_PATH` usage was left
    unquoted/unchanged — it's always `/data/local/tmp/enhancify/$PKG_NAME.apk`
    and Android package names can't contain spaces, so those sites were
    never actually vulnerable.
  - New `tests/test_rish_script.py::test_mv_quoting_survives_names_with_spaces_and_unicode`
    exercises the real shell script (not a Python re-implementation) via
    an `exported_name` param newly threaded through the existing stub-rish
    harness; the stub's `mv -f` case re-parses the received command string
    exactly like the real backend does (`eval "set -- $CMD"`) and reports
    the resulting word count. Confirmed the exact failure mode pre-fix via
    `git stash`: 8 words (path split apart) instead of the correct 4
    (`mv`, `-f`, source, dest). Full suite: 146/146 passing.
- Fixed (this session): the first successful bundle-app Rish install
  (Niagara Launcher, right after the Spoof-Signature fix above let it
  patch successfully for the first time) failed with `pm install`'s
  `INSTALL_FAILED_INVALID_APK: Failed to extract native libraries,
  res=-2`, reported live via `rish_log.txt`/`install_error.txt` from this
  device — a 5th, pre-existing bug in the same merge/optimize pipeline,
  exposed only because patching finally reached the install step for the
  first time this session.
  - Root cause: `android:extractNativeLibs=false` was set in the
    manifest, but the native `lib/*.so` entries were DEFLATE-compressed —
    an invalid combination (confirmed via `aapt2 dump xmltree` +
    `zipfile` inspection of the real merged APK). `false` means "mmap the
    libs directly from the APK, don't extract", which requires them
    stored uncompressed; `pm install`'s native-lib-extraction stage
    rejects the contradiction before ever reaching signature
    verification. `AntiSplitManager.antisplit_apkm/apks/xapk`
    (`src/antisplit.py`) run `APKEditor.jar m` with its default
    `-extractNativeLibs manifest` (auto-detect) mode, which produced the
    wrong result for this app's bundle (verified correct on a cached
    YouTube bundle, wrong on Niagara's — a third-party APKEditor
    behavior, not reproducible top-down, so not fully root-caused inside
    APKEditor itself). `optimize_native_libs`'s own zip-rebuild (the
    *default* single-APK path — `OPTIMIZE_LIBS` is on by default for any
    multi-ABI app, not just bundles) has the exact same defect
    independently: it force-compresses every file except `.arsc`,
    without regard for the original `extractNativeLibs` value — a latent
    landmine for any default-config multi-ABI app, found by inspection
    while fixing the bundle case (not yet reproduced as a user-facing
    failure, but mechanism-identical and confirmed via a synthetic
    fixture).
  - Fix: both `APKEditor.jar m` invocations now pass
    `-extractNativeLibs false` explicitly (APKEditor's own documented
    override: "set manifest attribute 'false' and store libraries
    un-compressed with 4096 alignment" — removes the ambiguity entirely,
    and uncompressed is valid Android-side regardless of what the
    original manifest declared). `optimize_native_libs`'s repackage now
    stores `lib/*.so` uncompressed too, matching `.arsc`.
  - Byte alignment of the now-uncompressed libs is intentionally **not**
    re-aligned locally: tried it (`zipalign -P 16 4` before
    `_sign_for_patching`) and found apksigner's v1 JAR signing reflows
    zip entry offsets regardless (27 of 37 libs ended up misaligned again
    after signing); tried aligning *after* signing instead and found the
    vendored `utils/zipalign` binary strips the APK Signing Block
    entirely when re-aligning an already-v2/v3-signed APK (not
    signing-block-aware). Resolved by relying on the downstream patch
    CLI's own "Aligning APK" pass instead, which is always in the
    pipeline (every antisplit/optimize output goes through `run_patch`
    before install, no shortcut path skips it) and was verified via a
    real end-to-end run to produce 0 misaligned libs regardless of the
    input's alignment state. The dead `_zipalign` helper was removed
    rather than left in as inert/misleading code.
  - Verified end-to-end on this device: re-ran the real
    `antisplit_apkm` → real CLI `patch` pipeline against a cached YouTube
    bundle. Final output: all 37 libs `compress_type=0` (stored), 0
    misaligned (`zipalign -c -P 16 4`), manifest `extractNativeLibs=false`
    consistent with storage, cert present pre-patch (confirms the Spoof
    Signature fix above still holds). New
    `tests/test_antisplit_signing.py::TestMergeForcesExtractNativeLibsFalse`
    (3 tests, pins the flag is actually passed to APKEditor for all three
    merge methods) and `::TestOptimizeNativeLibsStoresUncompressed` (pins
    native libs survive as stored/uncompressed). Confirmed all 4 fail
    pre-fix via `git stash`. Full suite: 150/150 passing.
- Fixed (this session): after the native-lib fix above, Niagara Launcher
  patched and the merge/lib pipeline was clean, but Rish install hit a
  6th, unrelated failure: `pm install` returned
  `INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package bitpit.launcher
  signatures do not match newer version; ignoring!` — and the TUI showed
  a dead-end generic error dialog instead of the uninstall+reinstall
  conflict prompt the user expected (it exists for the downgrade case,
  reported live via `rish_log.txt`/`install_error.txt`).
  - Not a bug in the signing/patch pipeline: this is standard Android
    behavior — an app already installed from the Play Store carries
    Google's/the developer's real signing certificate; any patched build
    (EnhanciPy's auto-managed `revancify.keystore`, or a user's configured
    custom keystore) is signed with a different one, and `pm install`
    correctly refuses to treat a differently-signed APK as an in-place
    update, regardless of `ALLOW_APP_VERSION_DOWNGRADE`/
    `BYPASS_LOW_TARGET_SDK_BLOCK`. No flag bypasses this; the only
    remedies are uninstall-then-install (loses app data) or installing
    alongside under a renamed package.
  - Real gap: `AppInstaller._rish_failure_result` (`src/installer.py`)
    only recognized `INSTALL_FAILED_VERSION_DOWNGRADE` as a resolvable
    conflict; `INSTALL_FAILED_UPDATE_INCOMPATIBLE` fell through to a
    plain error dialog with no way to proceed short of manually
    uninstalling outside the app. `uninstall_and_reinstall` was already
    fully generic (doesn't care why it's being called), so this was a
    missing-case gap, not a missing capability.
  - Fix: new `CONFLICT_SIGNATURE_MISMATCH` constant alongside
    `CONFLICT_VERSION_DOWNGRADE`; `_rish_failure_result` now maps
    `INSTALL_FAILED_UPDATE_INCOMPATIBLE` to it.
    `PatchProgressScreen` (`src/tui/screens/patch_progress.py`) gained
    `_prompt_signature_mismatch` (same uninstall+reinstall
    `ConfirmDialog`, wording explains *why* — different signing cert, not
    a version issue) alongside the existing `_prompt_downgrade`; both now
    share one `_on_conflict_confirm` callback (renamed from
    `_on_downgrade_confirm`, which had no downgrade-specific logic in its
    body — it just drives the already-generic
    `uninstall_and_reinstall`).
  - New `tests/test_installer.py::test_rish_signature_mismatch_failure_surfaces_conflict`
    and `tests/test_downgrade_dialog.py::test_signature_mismatch_conflict_prompts_then_runs_uninstall_reinstall`
    pin the mapping and the full conflict → dialog → retry wiring,
    mirroring the existing downgrade tests. Updated
    `test_installer.py::test_non_downgrade_failure_has_no_conflict`,
    which had incidentally used `INSTALL_FAILED_UPDATE_INCOMPATIBLE` as
    its example of an unhandled code — now genuinely unhandled
    (`INSTALL_FAILED_INSUFFICIENT_STORAGE`), since the old example is
    handled on purpose now. Confirmed both new tests fail pre-fix (hard
    `ImportError` on the new constant, since nothing partially existed).
    Full suite: 152/152 passing.
- Candidates for next session (not yet started), in priority order:
  1. **`CyberHeader` badge colors are dead code** — `mode_color`/
     `net_color` (`src/tui/widgets/header.py:64,68`) are computed from
     real privilege/network state but never applied to the `Label`s;
     badges always render via static `badge-green`/`badge-cyan` CSS
     classes regardless of state. `CyberStatusBar` applies its computed
     color correctly. Either wire the header badges up the same way, or
     delete the dead computation — needs a decision first.
  2. **Root-device Unmount-button path unverified live** — only a
     non-root Rish device was available this session;
     `privileges_resolved()` -> `unmount.display = priv[0]` has mocked
     test coverage only. Needs a smoke pass on a rooted device.
  3. **30s network-staleness tradeoff** — `check_network()`'s TTL means
     a screen opened right after a connectivity change can show a stale
     Online/Offline badge for up to 30s. By-design from this session,
     not a bug; worth a product call on whether polling is good enough
     or a push-based listener is warranted.


