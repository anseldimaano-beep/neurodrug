"""
fix_mojibake.py
----------------
Fixes double-encoded UTF-8 text (mojibake) across the NeuroDrug repo,
using the ftfy library, which fixes text segment-by-segment rather than
whole-file. That matters here because some files have a MIX of already-
correct Unicode characters and separately mojibake-corrupted ones (e.g.
a real box-drawing dash next to a garbled one) -- a naive whole-file
remap either wrecks the correct parts or refuses to touch the file.

USAGE (from repo root):
    pip install ftfy --break-system-packages   # or just: pip install ftfy
    python fix_mojibake.py            # scans and fixes
    python fix_mojibake.py --dry-run  # preview only, no writes
"""

import os
import sys

try:
    import ftfy
except ImportError:
    print("ftfy is not installed. Run: pip install ftfy")
    sys.exit(1)

EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".py", ".md", ".json", ".yml", ".yaml")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", ".venv", "venv"}

# Only fix genuine mojibake (wrong-encoding round-trips). Leave line endings,
# curly quotes, ligatures, and Unicode normalization untouched -- those are
# cosmetic ftfy features that could rewrite text that was never broken.
FIX_CONFIG = ftfy.TextFixerConfig(
    fix_line_breaks=False,
    uncurl_quotes=False,
    fix_latin_ligatures=False,
    fix_character_width=False,
    normalization=None,
)


def main():
    dry_run = "--dry-run" in sys.argv
    root = os.getcwd()
    print(f"Scanning for mojibake in {root} ...")

    changed = []

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(EXTENSIONS):
                continue
            path = os.path.join(current_root, fname)
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    raw = f.read()
            except (UnicodeDecodeError, OSError):
                continue

            fixed = ftfy.fix_text(raw, config=FIX_CONFIG)

            if fixed != raw:
                changed.append(path)
                if not dry_run:
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        f.write(fixed)

    if not changed:
        print("No mojibake found.")
    else:
        label = "(dry run - not modified)" if dry_run else "(fixed)"
        print(f"\nFiles with mojibake {label}:")
        for p in changed:
            print(f"  {p}")
        verb = "would be" if dry_run else "were"
        print(f"\n{len(changed)} file(s) {verb} updated.")


if __name__ == "__main__":
    main()
