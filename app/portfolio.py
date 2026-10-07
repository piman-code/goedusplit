"""Portfolio records: validate each file independently and preserve saved history."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import uuid


def read_snapshot(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("students"), list):
        raise ValueError("Invalid portfolio record")
    for field in ("subject", "grade", "semester", "saved_at"):
        if not isinstance(data.get(field, ""), (str, int, float)):
            raise ValueError("Invalid portfolio metadata")
    for student in data["students"]:
        if not isinstance(student, dict):
            raise ValueError("Invalid portfolio student")
        if not (student.get("student_hash") or student.get("sid") or student.get("name")):
            raise ValueError("Missing portfolio identity")
        score = float(student.get("final_score", 0) or 0)
        if not math.isfinite(score):
            raise ValueError("Invalid portfolio score")
    snapshot_signature(data)  # Reject nested non-finite values before rendering.
    return data


def snapshot_signature(data: dict) -> str:
    """Compare a current result to saved content without its creation timestamp."""
    fields = ("subject", "grade", "semester", "round", "cuts", "students")
    content = {key: data.get(key) for key in fields}
    return json.dumps(content, ensure_ascii=False, sort_keys=True, allow_nan=False)


def write_snapshot(store: Path, snapshot: dict) -> Path:
    subject = re.sub(r'[\x00-\x1f\\/:*?"<>|]+', "_", str(snapshot.get("subject", "subject")))
    subject = subject.strip(" .")[:80] or "subject"
    # A unique, exclusively created file never overwrites an earlier save.
    name = str(snapshot["saved_at"]).replace(":", "").replace("-", "")
    path = store / f"{name}_{subject}_{uuid.uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False))
        stream.write("\n")
    return path
