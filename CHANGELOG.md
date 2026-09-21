# EnhanciPy Changelog

## [v1.1.0] — theme persistence fix + rish downgrade-conflict resolution

### Fixed

- **Theme choice no longer resets.** The test suite was writing straight to
  the live `.config` file (no test isolation), so running `pytest` reverted
  whatever theme you'd picked back to Cybernetic Green. Tests now run
  against a throwaway sandboxed config; your selected theme survives every
  relaunch.

### Added

- **Version-downgrade conflict dialog.** Installing a patched APK with a
  lower version code than the currently installed app used to fail with a
  generic Rish error. It now detects `INSTALL_FAILED_VERSION_DOWNGRADE` and
  offers a clear Yes/No dialog (green Yes, red No, legible in every theme)
  to uninstall the current version and install the patched one in a single
  flow.
- **Settings ▸ Allow Version Downgrades is now wired up.** When enabled, the
  Rish installer first tries a data-preserving `pm install -d`; the
  uninstall-and-reinstall prompt only appears if that still fails.

## [v1.0.0] — first release

EnhanciPy is a pure-Python Textual TUI for patching Android apps on Termux.
It is a full rewrite of the Enhancify bash/dialog tool (itself a fork of
Revancify), based on Enhancify v6.2.6, modded by jair-00.

### What it does

- Downloads a patch source's ReVanced-style CLI + patch bundle, picks an app
  and version, and patches it — all inside Termux, no PC required.
- Fetches APKs from APKMirror with version tags (RECOMMENDED / INSTALLED /
  STABLE / BETA), or imports a local APK / APKM / APKS / XAPK.
- Merges split bundles (APKM/APKS/XAPK) with APKEditor and strips unused
  native ABIs with aapt2.
- Signs with the bundled apksigner + BouncyCastle, or your own keystore, and
  installs via root mount, Shizuku `rish`, or plain export to storage.
- Manages extra dependencies (GmsCore, PotHelper), GitHub tokens, custom
  patch sources, bundle patchers, and stock-app backups.

### Differences from Enhancify v6.2.6

- The bash/`dialog` UI is gone. The whole interface is Textual: real
  scrolling, long-press patch descriptions, animated toggles, gradient
  download gauges, and live progress on every long operation.
- Every colour comes from one ~14-value theme token palette, so switching a
  theme repaints the running screen instantly.
- Layout is verified at 40×25 through 120×40, so it fits a portrait phone.
- `bin/aapt2` and `bin/APKEditor.jar` are downloaded on first launch from
  this project's own release assets instead of third-party repositories, and
  can be re-fetched from Configure ▸ Runtime Dependencies.
- The GmsCore directory is `Dependencies/`, holding both GmsCore and
  PotHelper, always resolved to the latest published APK.
