<div align="center">

<img src="docs/logo.svg" alt="EnhanciPy" width="560">

**Patch Android apps right on your phone, from a terminal UI in Termux.**

[![Release](https://img.shields.io/github/v/release/jairjacom/Enhancipy?label=release&color=2ea043)](https://github.com/jairjacom/Enhancipy/releases/latest)
[![Last commit](https://img.shields.io/github/last-commit/jairjacom/Enhancipy?color=blue)](https://github.com/jairjacom/Enhancipy/commits/main)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)

Python-only fork of [Enhancify](https://github.com/Graywizard888/Enhancify), itself a fork of Revancify.

</div>

## What it does

EnhanciPy downloads an app, applies the patches you pick, signs it and, if
you allow it, installs the result. You never leave Termux.

<!-- FEATURES:START -->
### Patching

| Feature | What it does | Needs | Since |
| --- | --- | --- | --- |
| **Patch Android apps in Termux** | Pick an app, a version and the patches you want, then patch and sign it, all from a terminal UI on your phone. | Nothing extra | v1.0.0 |
| **Install it for you** | Install the patched app through root or Shizuku (rish), including a prompt to resolve version-downgrade conflicts. | Root or Shizuku | v1.0.0 |

### Sources

| Feature | What it does | Needs | Since |
| --- | --- | --- | --- |
| **Manage Sources** | One screen lists every patch source, repositories and imported files alike. Add or delete any of them and the changes stay after updates. | Nothing extra | v1.7.0 |
| **Import Patch File** | Use a `.mpp` patch bundle from your device as a source. The matching patcher is picked or downloaded for you. | Storage access | v1.4.0 |
| **Older Versions** | Pin one of a source's 5 newest releases as a local source that stays on that version until you delete it. | Nothing extra | v1.8.0 |

### Getting the app

| Feature | What it does | Needs | Since |
| --- | --- | --- | --- |
| **Bundle apps (APKM, APKS, XAPK)** | Apps that APKMirror serves as bundles are merged into one APK before patching, and install correctly afterwards. | Nothing extra | v1.3.7 |
| **Download in your browser when APKMirror blocks an app** | When APKMirror's browser check stops an automatic download, EnhanciPy opens the right page in your browser, marks the version your patch source targets, and carries on once the file lands in Downloads. It then brings Termux back to the front. | Storage access, Display over other apps | v1.9.0 |

### Look and feel

| Feature | What it does | Needs | Since |
| --- | --- | --- | --- |
| **10 themes** | From Cybernetic Green to Tokyo Night and OLED Midnight, with readable text and thin scrollbars in every one. Dialogs and lists fit small screens. | Nothing extra | v1.5.0 |
| **Automatic updates** | EnhanciPy checks for a newer version on every start and installs it. Turn it off in Configure, Features, Auto Update. | Nothing extra | v1.3.0 |
<!-- FEATURES:END -->

## Requirements and permissions

Patching works with nothing extra. The table lists what the extra features need.

<!-- REQUIREMENTS:START -->
| Permission or tool | Needed for | How to set it up |
| --- | --- | --- |
| **Storage access** | Required | Run `termux-setup-storage` once in Termux and allow the prompt. |
| **Display over other apps** | Optional | Android Settings, Apps, Termux, Display over other apps: turn it on. Without it you switch back to Termux by hand. |
| **Root or Shizuku** | Optional | Only to install the patched app for you. Use `su`, or Shizuku running with its `rish` shell copied into Termux. Patching alone needs neither. |
<!-- REQUIREMENTS:END -->

Core tools: Termux, `git`, Python 3.9+ and `java` (for signing and aligning
APKs). `aria2c` is optional and makes downloads faster.

## Quick start

```
pkg install git python openjdk-17 aria2
git clone https://github.com/jairjacom/Enhancipy.git
cd Enhancipy
pip install -r requirements.txt
python main.py
```

Optional flags:

```
python main.py --root        # force root (su) install mode
python main.py --rish        # force Shizuku (rish) install mode
python main.py --no-update   # skip the automatic update check
```

## First run

On first start, EnhanciPy automatically downloads the two helper tools it
needs (an architecture-matched `aapt2` binary and `APKEditor.jar`) from this
project's GitHub Releases into its `bin/` folder. This is expected behavior,
needs roughly 12 MB of free space, and happens once.

## Installing patched apps

Patching works without special privileges. To let EnhanciPy install the
patched APK for you, you need either root (`su`) or the Shizuku app running
on your device with its `rish` shell copied into Termux (see the Shizuku
app's own instructions for enabling that).

## Changes

Every release is listed in [CHANGELOG.md](CHANGELOG.md).

<div align="center">

[![Telegram](https://img.shields.io/badge/Telegram-Join%20the%20group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/jair00den)
[![Latest Stable](https://img.shields.io/github/v/release/jairjacom/Enhancipy?style=for-the-badge&label=Latest%20Stable&color=2ea043)](https://github.com/jairjacom/Enhancipy/releases/latest)
[![Stars](https://img.shields.io/github/stars/jairjacom/Enhancipy?style=for-the-badge&color=e3b341)](https://github.com/jairjacom/Enhancipy/stargazers)
[![Open Issues](https://img.shields.io/github/issues/jairjacom/Enhancipy?style=for-the-badge&label=Open%20Issues&color=d73a4a)](https://github.com/jairjacom/Enhancipy/issues)

</div>
