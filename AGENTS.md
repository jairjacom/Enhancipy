# AGENTS.md — EnhanciPy
Python Textual TUI for patching Android apps in Termux (fork of Enhancify/Revancify).
Read NOTES.md before touching rish, the install flow, or dependencies.

## Test
- `python -m pytest tests -q` from repo root. No CI: run before every merge.
- Device-facing changes (rish, install) are not proven by green tests. Verify on a real device and log before/after in NOTES.md.

## rish
- Always exits 0. Judge success from output text, never the return code.
- Detect with an echo-marker round trip.
- Unset RISH_APPLICATION_ID = silent no-op. Use `run_rish()` / `rish_environ()` in src/utils.py.
- Output starts with an "Entering shell..." banner. Strip it before parsing.
- Probes need generous timeouts (round trip is ~1s).

## Config and deps
- Config path comes from the `ENHANCIFY_CONFIG_FILE` env var (spelled FY). Python sets it when calling system/rish-install.sh; the script falls back to a path relative to itself. Never hardcode workspace directory names in system/*.sh.
- Env var names are inconsistent on purpose (rebrand touched visible text only): `ENHANCIFY_CONFIG_FILE`, `ENHANCIFY_BOOT_SECONDS`, `ENHANCIFY_ART`, `ENHANCIPY_DEP_BOOTSTRAP`. Do not rename them.
- bin/aapt2 and bin/APKEditor.jar: presence-only check. `git pull` never re-fetches them.

## Tests
- Config/theme state must stay sandboxed (autouse fixture in tests/conftest.py).
- Shell-script behavior: test the real .sh with a stub binary (tests/test_rish_script.py).
- Textual overflow: check `show_vertical_scrollbar`, not height comparisons.

## Branding
- Rebrand visible strings only. Never rename identifiers, paths, env vars, config keys, repo slug, User-Agent, or keystore alias.

## Git
Workflow, in order — do not skip or reorder steps:
1. Create `fix/<name>` or `feat/<name>` locally. Never commit directly on `main`; never merge into local `main` before step 9. Related fixes may share one branch/PR — separate commits, one PR at the end — instead of one branch/PR per fix.
2. Implement, then run `python -m pytest tests -q` on the branch. Fix and re-run until green before moving on.
3. For device-facing changes: log before/after in NOTES.md.
4. Hand off to the user: state the fix is applied and validated (tests green, NOTES.md logged if applicable) and what to verify. This is the agent-to-human handoff.
5. The user tests on that branch (the working tree already is the test env — no local merge needed to "install" it) and returns the handoff as confirmed or rejected.
6. If rejected, or a gate fails, keep iterating with more commits on the same branch. `main` is untouched the whole time, so there is nothing to undo.
7. Once the user confirms, push the branch and open a PR (`gh pr create`) — every change gets visible history/diff on GitHub.
8. Stop and ask the user to confirm before merging. Never merge or push `main` without an explicit OK.
9. On confirmation, merge the PR (`gh pr merge --squash` or `--merge`, matching the repo's existing merge-commit style) and delete the branch, both remote and local, in the same step (`gh pr merge --delete-branch`).
10. Sync local `main` with `git checkout main && git pull` — this is the only point local `main` advances, so it always matches `origin/main` exactly (avoids history divergence from a local merge plus a later squash-merge).

- Commit subject: imperative, no period. Body: root cause first, then the fix. Fix commits end with a verification line.
- Release = separate `changelog: vX.Y.Z - summary` commit right after the change, then tag vX.Y.Z. Never reuse tag `deps-v1`. Mandatory for every user-visible change — do it in the same session/PR chain, immediately after that PR merges. An external task/plan calling this "later," "mechanical tail," or "out of scope" does NOT defer it; finish it before reporting the change done, or state explicitly that you are deferring it and why.
- Every `changelog: vX.Y.Z` commit must also bump `.info` to the same version; tests/test_version_sync.py enforces that `.info` matches the newest CHANGELOG.md heading.
- Bugfixes with no user-visible impact get no version bump.

## CHANGELOG.md (read by end users)
- Newest first: `## [vX.Y.Z] — summary`, then `### Added` / `### Fixed`.
- Plain language: what was wrong, what's better now. No file paths, function names, env vars, or error constants. Dev detail goes in the commit body or NOTES.md.
