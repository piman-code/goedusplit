"""Print the source app version for packaging without importing its UI."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import __version__


def main():
    if not isinstance(__version__, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)[.](?:0|[1-9][0-9]*)", __version__):
        print("Invalid app version: expected numeric major.minor.patch", file=sys.stderr)
        return 1
    print(__version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
