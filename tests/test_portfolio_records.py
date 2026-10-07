import json
from pathlib import Path
import tempfile
import unittest

from app.portfolio import read_snapshot, snapshot_signature, write_snapshot


class PortfolioRecordTests(unittest.TestCase):
    def record(self):
        return {"saved_at": "2026-10-07T12:00:00", "subject": "합성과목",
                "semester": "1학기", "grade": "1", "round": 1,
                "students": [{"student_hash": "abc123", "final_score": 90}]}

    def test_two_saves_in_one_second_preserve_both_files(self):
        with tempfile.TemporaryDirectory() as root:
            store = Path(root)
            first = write_snapshot(store, self.record())
            original = first.read_bytes()
            second_record = self.record()
            second_record["students"][0]["final_score"] = 70
            second = write_snapshot(store, second_record)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(read_snapshot(second)["students"][0]["final_score"], 70)

    def test_signature_distinguishes_round_and_score_but_not_save_time(self):
        record = self.record()
        other = self.record()
        other["saved_at"] = "2026-10-08T12:00:00"
        self.assertEqual(snapshot_signature(record), snapshot_signature(other))
        other["round"] = 2
        self.assertNotEqual(snapshot_signature(record), snapshot_signature(other))
        other = self.record()
        other["students"][0]["final_score"] = 70
        self.assertNotEqual(snapshot_signature(record), snapshot_signature(other))

    def test_corrupt_shapes_and_nonfinite_scores_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            for index, data in enumerate(([1], {}, {"students": "bad"}, {"students": [5]},
                      {"students": [{"student_hash": "abc", "final_score": "NaN"}]},
                      {"subject": {}, "students": []})):
                path = Path(root) / f"bad-{index}.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises((ValueError, TypeError)):
                    read_snapshot(path)

    def test_utf8_bom_and_legacy_identity_remain_readable(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "legacy.json"
            path.write_text(json.dumps({"version": 1, "students": [
                {"sid": "synthetic-1", "class_no": "1/1", "name": "합성학생", "final_score": 50}]}),
                encoding="utf-8-sig")
            self.assertEqual(read_snapshot(path)["version"], 1)
