# EnhanciPy Changelog

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
