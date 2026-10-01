"""앱 진입점.

사용:
    python run.py
"""
from __future__ import annotations

import os
import sys


def _configure_frozen_webengine() -> None:
    if not getattr(sys, "frozen", False):
        return
    defaults = [
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
        "--disable-zero-copy",
    ]
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    merged = existing.split()
    for flag in defaults:
        if flag not in merged:
            merged.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged)


_configure_frozen_webengine()

if __name__ == "__main__":
    if "--synthetic-qa" in sys.argv:
        from app.synthetic_qa import main
        raise SystemExit(main())
    from app.main_window import run
    run()
