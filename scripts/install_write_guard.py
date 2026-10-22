#!/usr/bin/env python3
"""RHC HWB-01 local write-guard installer.

Idempotently activates the local BUILD commit fence for this clone by pointing
`core.hooksPath` at the repository's `.githooks` directory. Refuses to trample
any unrelated hook configuration: a different local `core.hooksPath`, an
inherited global/system `core.hooksPath` that a local setting would silently
override, or any old-style hook file (`pre-commit`, `pre-push`, `commit-msg`,
...) in the actual current hooks directory (resolved through Git so linked
worktrees are handled correctly, not assumed to be `<checkout>/.git/hooks`)
that redirecting `core.hooksPath` would silently disable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HOOKS_DIR = ".githooks"


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _effective_hookspath():
    """Return (origin, value) for the effective core.hooksPath, or (None, None).

    `--show-origin` exposes whether the effective value comes from this
    repository's local config or an inherited global/system config, so the
    installer can refuse to silently override an unrelated hook suite.
    """
    proc = _git("config", "--show-origin", "--get", "core.hooksPath")
    if proc.returncode != 0 or not proc.stdout.strip():
        return None, None
    origin, _, value = proc.stdout.rstrip("\n").partition("\t")
    return origin, value


def _is_local_hooks_path_active() -> bool:
    """True only when THIS repository's local config sets the RHC hooks path.

    An inherited global/system `core.hooksPath` (even with the same value) is
    not local, so the installer will refuse rather than shadow it.
    """
    proc = _git("config", "--local", "--get", "core.hooksPath")
    return proc.returncode == 0 and proc.stdout.strip() == HOOKS_DIR


def _existing_hooks_dir() -> Path | None:
    """Resolve the actual current hooks directory, or None if there is none.

    Uses `git rev-parse --git-path hooks` rather than assuming
    `<checkout>/.git/hooks`: in a linked worktree, `.git` is a pointer file,
    not the Git directory, and hooks normally live in the shared common Git
    directory. Resolving through Git keeps existing-hook detection correct
    in that layout too.
    """
    proc = _git("rev-parse", "--git-path", "hooks")
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    path = Path(proc.stdout.strip())
    return path if path.is_dir() else None


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    if not (here / HOOKS_DIR / "pre-commit").is_file():
        print(f"INSTALL REFUSED: {HOOKS_DIR}/pre-commit not found", file=sys.stderr)
        return 1

    origin, current = _effective_hookspath()
    if current is not None:
        if current == HOOKS_DIR and _is_local_hooks_path_active():
            print(f"WRITE GUARD ALREADY ACTIVE: core.hooksPath = {HOOKS_DIR}")
            return 0
        print(
            f"INSTALL REFUSED: effective core.hooksPath is '{current}' "
            f"(origin: {origin or 'unknown'}); refusing to trample an "
            f"unrelated hook configuration",
            file=sys.stderr,
        )
        return 1

    # Switching to core.hooksPath redirects lookup for EVERY hook, not just
    # pre-commit, so any other existing hook file (pre-push, commit-msg, ...)
    # would be silently disabled unless we check for it here too.
    hooks_dir = _existing_hooks_dir()
    if hooks_dir is not None:
        sample = (here / HOOKS_DIR / "pre-commit").read_bytes()
        for entry in sorted(hooks_dir.iterdir()):
            if not entry.is_file() or entry.name.endswith(".sample"):
                continue
            if entry.name == "pre-commit":
                if entry.read_bytes().strip() != sample.strip():
                    print(
                        f"INSTALL REFUSED: an unrelated {entry} exists "
                        "and switching to core.hooksPath would bypass it",
                        file=sys.stderr,
                    )
                    return 1
                continue
            print(
                f"INSTALL REFUSED: an unrelated hook {entry} exists and "
                "switching to core.hooksPath would silently disable it",
                file=sys.stderr,
            )
            return 1

    proc = _git("config", "--local", "core.hooksPath", HOOKS_DIR)
    if proc.returncode != 0:
        print(f"INSTALL REFUSED: could not set core.hooksPath: {proc.stderr}",
              file=sys.stderr)
        return 1
    print(f"WRITE GUARD INSTALLED: core.hooksPath = {HOOKS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
