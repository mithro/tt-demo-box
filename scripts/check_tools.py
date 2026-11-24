"""Check that the external tools the build needs are installed."""

import shutil
import subprocess
import sys

TOOLS = ("inkscape", "blender")
FIX = "sudo apt install inkscape blender"


def main() -> int:
    missing = []
    for tool in TOOLS:
        if shutil.which(tool) is None:
            missing.append(tool)
            continue
        out = subprocess.run([tool, "--version"], capture_output=True, text=True, check=True)
        print(f"{tool}: {out.stdout.strip().splitlines()[0]}")
    if missing:
        print(f"missing: {', '.join(missing)}; fix: {FIX}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
