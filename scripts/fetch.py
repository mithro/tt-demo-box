#!/usr/bin/env python3
"""Fetch upstream sources into tmp/src (run: make fetch).

Each source is shallow-cloned at a pinned commit, so a rerun reproduces the
same files; the commit actually checked out is printed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tmp" / "src"

#: name -> (repo URL, pinned commit)
SOURCES = {
    "tiny-vga": ("https://github.com/mole99/tiny-vga",
                 "a081ae634119aae719237aee5c6b5e53549d1c81"),
}


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def fetch(name: str, url: str, commit: str) -> str:
    dest = SRC / name
    if not (dest / ".git").exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        git("init", "-q", str(dest))
        git("remote", "add", "origin", url, cwd=dest)
    if subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=dest, capture_output=True).returncode:
        git("fetch", "--depth", "1", "origin", commit, cwd=dest)
    git("checkout", "-q", "--detach", commit, cwd=dest)
    return git("rev-parse", "HEAD", cwd=dest)


def main() -> None:
    for name, (url, commit) in SOURCES.items():
        print(f"{name}: {url} @ {fetch(name, url, commit)}")


if __name__ == "__main__":
    main()
