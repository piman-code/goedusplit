#!/usr/bin/env python3
"""Prepare a new, synthetic-only school handoff around the immutable candidate.

No network, installation, existing settings, or arbitrary school inputs are used.
Run with the existing development Python environment; Windows needs only the
resulting bundle and its built-in PowerShell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = "1.0.6"
COMMIT = "65cfc79268b00aaf2077e094c2e24e37b12bcdbc"
ZIP_NAME = "Goedu-Split-1.0.6-windows.zip"
ZIP_HASH = "9852262fc23195f41625c3a051e1743b1ddc6765ed9a9437260b10437e67d8d3"
DOCS = (
    "docs/WINDOWS_SCHOOL_QA.md", "docs/SYNTHETIC_VALIDATION.md",
    "docs/PC_VALIDATION_RECORD.md", "docs/AUTONOMOUS_COMPLETION.md",
    "docs/DEVELOPMENT_PLAN.md", "docs/DEVELOPMENT.md",
    "docs/RELEASE_CANDIDATES.md", "docs/BACKUP_AND_ROLLBACK.md",
    "docs/VERIFICATION_20261002.md", "docs/GOAL_STATUS.md", "docs/HANDOFF.md",
    "distribution/MANUAL_QA_CHECKLIST.md", "distribution/USER_GUIDE.md",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_new(path):
    # Use an absolute spelling without resolving away symlinks/junctions.
    path = path.expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            if (sys.platform == "darwin" and part in (Path("/tmp"), Path("/var"))
                    and part.resolve() == Path("/private") / part.name):
                continue
            raise ValueError("Output and parents must not be links")
    if path.exists():
        raise FileExistsError("Output exists; nothing will be overwritten")
    return path


def prepare(candidate_dir, output):
    output = check_new(output)
    archive_path = check_new(output.parent / (output.name + ".zip"))
    candidate = candidate_dir / ZIP_NAME
    if candidate.is_symlink() or not candidate.is_file() or digest(candidate) != ZIP_HASH:
        raise ValueError("Expected immutable Windows candidate checksum does not match")
    sources = [ROOT / name for name in DOCS]
    sources.append(ROOT / "build_scripts/validate_school_candidate.ps1")
    if any(not path.is_file() or path.is_symlink() for path in sources):
        raise ValueError("A required tracked handoff file is missing or is a link")
    # All generated inputs are authored synthetic fixtures, never supplied files.
    from build_scripts.generate_synthetic_validation_kit import generate
    output.mkdir(parents=True, exist_ok=False)
    generate(output / "synthetic")
    for source in sources:
        destination = output / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    with candidate.open("rb") as incoming, (output / ZIP_NAME).open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    if digest(output / ZIP_NAME) != ZIP_HASH:
        raise ValueError("Copied candidate differs from its pinned checksum; output preserved")
    (output / "START_HERE.txt").write_text(
        "Goedu-Split 1.0.6 - school Windows check (no installation)\n"
        "1. Extract this entire handoff ZIP with Windows 'Extract All'.\n"
        "2. Open PowerShell in the extracted folder.\n"
        "3. Run:\n"
        "powershell.exe -NoProfile -File .\\build_scripts\\validate_school_candidate.ps1 "
        "-CandidateZip .\\Goedu-Split-1.0.6-windows.zip -OutputRoot .\\school-result-01 "
        "-Context School\n"
        "4. Read docs/WINDOWS_SCHOOL_QA.md for results and manual acceptance.\n"
        "A blocked script must be reported; do not change school security settings.\n"
        "Use a different new output name for another run.\n"
        "Synthetic only. Excel/teacher/installation/round-trip acceptance remains separate.\n",
        encoding="utf-8",
    )
    hashes = {p.relative_to(output).as_posix(): digest(p)
              for p in sorted(output.rglob("*")) if p.is_file()}
    manifest = {
        "candidate_version": VERSION, "candidate_source_commit": COMMIT,
        "candidate_zip_sha256": ZIP_HASH,
        "runner_sha256": hashes["build_scripts/validate_school_candidate.ps1"],
        "inputs": "freshly generated synthetic only",
        "school_acceptance": "pending actual school execution and human acceptance",
        "file_sha256": hashes,
        "hash_scope": "all handoff files except HANDOFF_MANIFEST.json",
    }
    (output / "HANDOFF_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Candidate ZIP is already compressed; do not spend time recompressing it.
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(output.name) / path.relative_to(output)).as_posix())
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Handoff ZIP integrity failed; preserved for diagnosis")
    for name, checksum in hashes.items():
        if digest(output / name) != checksum:
            raise ValueError("Handoff file changed during collection")
    return {"status": "prepared", "candidate_source_commit": COMMIT,
            "file_count": len(hashes) + 1, "bundle_zip_sha256": digest(archive_path),
            "folder": str(output), "archive": str(archive_path),
            "school_acceptance": "not executed by bundle generation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.candidate_dir, args.output), ensure_ascii=False, indent=2))
    except Exception as error:
        print("Handoff preparation failed: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
