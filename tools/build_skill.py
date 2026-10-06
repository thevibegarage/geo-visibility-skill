#!/usr/bin/env python3
"""Build dist/geo-visibility.skill: a zip of the geo-visibility/ folder (without evals, tests or caches).

Usage:
    python tools/build_skill.py [output.skill]

Attach the result to a GitHub release so Claude web/desktop users can install it. The release asset is
not rebuilt automatically: rebuild and re-upload it whenever the skill changes.
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = "geo-visibility"
EXCLUDE_DIRS = {"__pycache__", "evals", ".git"}
EXCLUDE_FILES = {".DS_Store"}


def files():
    base = os.path.join(ROOT, SKILL)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        for name in sorted(filenames):
            if name in EXCLUDE_FILES or name.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, name)
            yield full, os.path.join(SKILL, os.path.relpath(full, base)).replace(os.sep, "/")


def build(out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for full, arc in files():
            z.write(full, arc)
    return out


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", f"{SKILL}.skill")
    build(target)
    with zipfile.ZipFile(target) as z:
        print(f"built {target} ({len(z.namelist())} files)")
