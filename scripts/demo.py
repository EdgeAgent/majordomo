"""Standalone demo — run the scripted day without installing anything.

    python scripts/demo.py

Adds ``src/`` to the path and calls the same demo the ``majordomo demo``
command runs: the fake provider, fake backends, a throwaway data dir.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from majordomo.demo import main

if __name__ == "__main__":
    main()
