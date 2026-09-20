# Enhancify

A Textual TUI for patching Android apps on Termux.

## Requirements

- Termux
- Python 3.9+
- `java` (for signing/aligning APKs)
- `aria2c` (optional, faster parallel downloads)
- `su` or Shizuku's `rish` (optional, required for root/Shizuku install modes)

## Install

```
pkg install python openjdk-17 aria2
pip install -r requirements.txt
```

## Run

```
python main.py
python main.py --root
python main.py --rish
python main.py --smoke-test
```

## Tests

```
python -m pytest tests -q
```

Run from the repo root — the tests import `src.*`, so the current working
directory must be the repo root.

## About

This is a Python-only fork of Enhancify (itself a fork of Revancify); the
legacy bash dialog UI is not included. `system/*.sh` are the only shell
helpers that remain, used for root mount, Rish install, and unmount.
