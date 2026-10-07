"""Run synthetic tests with the same isolation as direct unittest discovery."""
from __future__ import annotations

import sys
import unittest
import argparse
import os
from pathlib import Path
from tests.runtime_isolation import ensure_isolated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--pattern", default="test_*.py")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    if os.environ.get("GOEDUSPLIT_RETAIN_TEST_FILES") == "1":
        import uuid
        os.environ["GOEDUSPLIT_TEST_EVIDENCE_ROOT"] = str(Path(os.environ.get("RUNNER_TEMP", str(project.parent))) / ("test-evidence-" + uuid.uuid4().hex))
    if os.environ.get("GOEDUSPLIT_TEST_EVIDENCE_ROOT"):
        from build_scripts.preserve_synthetic_files import enable
        enable(os.environ["GOEDUSPLIT_TEST_EVIDENCE_ROOT"])
    root = ensure_isolated()
    print("Synthetic tests: temporary settings, app data, caches, AI workdir; network blocked.", flush=True)
    suite = unittest.defaultTestLoader.discover(str(project / "tests"), pattern=args.pattern, top_level_dir=str(project))
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    raise SystemExit(not result.wasSuccessful())
