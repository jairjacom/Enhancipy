# EnhanciPy

A Textual TUI for patching Android apps on Termux.
Python-only fork of Enhancify (itself a fork of Revancify).

## Requirements

- Termux
- `git`
- Python 3.9+
- `java` (for signing and aligning APKs)
- `aria2c` (optional — faster parallel downloads)
- `su` or Shizuku's `rish` (optional — only needed for root/Shizuku
  install modes; patching alone needs neither)

## Install

```
pkg install git python openjdk-17 aria2
git clone https://github.com/jairjacom/Enhancipy.git
cd Enhancipy
pip install -r requirements.txt
```

## Run

```
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
needs — an architecture-matched `aapt2` binary and `APKEditor.jar` — from
this project's GitHub Releases into its `bin/` folder. This is expected
behavior, needs roughly 12 MB of free space, and happens once.

## Installing patched apps

Patching works without special privileges. To let EnhanciPy install the
patched APK for you, you need either root (`su`) or the Shizuku app running
on your device with its `rish` shell copied into Termux (see the Shizuku
app's own instructions for enabling that).
