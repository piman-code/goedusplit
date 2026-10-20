"""Versioned local work snapshots. No pickle, original-file copies or network.

Unlike hashed summary history, an explicitly saved full work snapshot contains
student identities/responses so the teacher can resume the original analysis.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

from .data_loader import ExamData, ItemInfo, StudentResponse
from .perform_loader import PerformArea, PerformData, PerformRecord
from .analysis import analyze_items, analyze_overall, build_score_matrix

MAX_BYTES = 64 * 1024 * 1024
TYPES = {c.__name__: c for c in (ExamData, ItemInfo, StudentResponse, PerformArea, PerformData, PerformRecord)}


def _encode(value):
    if dataclasses.is_dataclass(value):
        return {"type": type(value).__name__, "fields": {
            f.name: _encode(getattr(value, f.name)) for f in dataclasses.fields(value)}}
    if isinstance(value, dict):
        return {"pairs": [[_encode(k), _encode(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("작업에 저장할 수 없는 숫자가 있습니다.")
        return value
    raise ValueError("지원하지 않는 작업 데이터 형식입니다.")


def _decode(value, depth=0):
    if depth > 40:
        raise ValueError("작업 데이터 구조가 너무 깊습니다.")
    if isinstance(value, list):
        return [_decode(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if set(value) == {"pairs"} and isinstance(value["pairs"], list):
            result = {}
            for pair in value["pairs"]:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("잘못된 작업 데이터입니다.")
                k, v = (_decode(x, depth + 1) for x in pair)
                if not isinstance(k, (str, int)) or isinstance(k, bool) or k in result:
                    raise ValueError("중복되거나 잘못된 작업 키입니다.")
                result[k] = v
            return result
        if set(value) == {"type", "fields"} and value["type"] in TYPES:
            cls = TYPES[value["type"]]
            fields = value["fields"]
            if not isinstance(fields, dict) or set(fields) != {f.name for f in dataclasses.fields(cls)}:
                raise ValueError("작업 데이터 필드가 일치하지 않습니다.")
            return cls(**{k: _decode(v, depth + 1) for k, v in fields.items()})
        raise ValueError("알 수 없는 작업 데이터 형식입니다.")
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("유효하지 않은 숫자입니다.")
        return value
    raise ValueError("유효하지 않은 작업 값입니다.")


def encode_domain(exam, perform_data=None):
    return {"exam": _encode(exam), "perform_data": _encode(perform_data)}


def build_session(exam, perform_data, ui_state, calculator_project, metadata=None):
    payload = {"kind": "work-session", "version": 1,
               "saved_at": datetime.now().isoformat(timespec="seconds"),
               "metadata": dict(metadata or {}), "domain": encode_domain(exam, perform_data),
               "ui_state": ui_state, "calculator_project": calculator_project}
    payload["metadata"].setdefault("subject", exam.subject)
    return validate_session(payload)


def validate_session(payload):
    if not isinstance(payload, dict) or payload.get("kind") != "work-session":
        raise ValueError("요약 전용 기록은 전체 작업으로 복원할 수 없습니다.")
    if payload.get("version") != 1:
        raise ValueError("지원하지 않는 작업 저장 버전입니다.")
    required = {"kind", "version", "saved_at", "metadata", "domain", "ui_state", "calculator_project"}
    if set(payload) != required or not isinstance(payload["ui_state"], dict) or not isinstance(payload["metadata"], dict):
        raise ValueError("작업 저장 항목이 누락되었거나 잘못되었습니다.")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("작업에 유효하지 않은 값이 있습니다.") from exc
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise ValueError("작업 저장 크기가 제한을 넘었습니다.")
    domain = payload["domain"]
    if not isinstance(domain, dict) or set(domain) != {"exam", "perform_data"}:
        raise ValueError("분석 자료가 누락되었습니다.")
    exam, perform = _decode(domain["exam"]), _decode(domain["perform_data"])
    if not isinstance(exam, ExamData) or not exam.students:
        raise ValueError("분석한 학생 자료가 필요합니다.")
    if not all(isinstance(v, StudentResponse) for v in exam.students) or not all(isinstance(v, ItemInfo) for v in exam.items):
        raise ValueError("학생·문항 자료 형식이 다릅니다.")
    if perform is not None and not isinstance(perform, PerformData):
        raise ValueError("수행평가 자료 형식이 다릅니다.")
    if not isinstance(exam.cut_scores, dict) or set(exam.cut_scores) != set("ABCDE"):
        raise ValueError("분할점수가 누락되었습니다.")
    for value in exam.cut_scores.values():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError("분할점수가 올바르지 않습니다.")
    project = payload["calculator_project"]
    if project is not None and (not isinstance(project, dict) or not isinstance(project.get("items"), list)
                                or not isinstance(project.get("judges"), list)):
        raise ValueError("예상정답률 편집 상태가 올바르지 않습니다.")
    return json.loads(encoded)


def prepare_session(payload):
    payload = validate_session(payload)
    exam = _decode(payload["domain"]["exam"])
    perform = _decode(payload["domain"]["perform_data"])
    try:
        score_mat, _, _ = build_score_matrix(exam)
        overall = analyze_overall(exam, score_mat)
        items = analyze_items(exam)[0]
    except Exception as exc:
        raise ValueError("저장된 분석 자료를 검증하지 못했습니다.") from exc
    return {"exam": exam, "perform_data": perform, "overall": overall, "item_stats": items,
            "ui_state": payload["ui_state"], "calculator_project": payload["calculator_project"],
            "metadata": payload["metadata"]}


def signature(payload):
    content = {k: v for k, v in payload.items() if k not in {"saved_at", "metadata"}}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class WorkSessionStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def save(self, payload):
        payload = validate_session(payload)
        content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
        self.directory.mkdir(parents=True, exist_ok=True)
        name = f"work_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}"
        pending, final = self.directory / (name + ".pending"), self.directory / (name + ".json")
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # An exclusive hard link publishes complete bytes without overwriting any
        # prior file. Retain the pending hard link as recovery evidence.
        os.link(pending, final)
        return final

    def read(self, path):
        path = Path(path)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("작업 파일이 너무 큽니다.")
        return validate_session(json.loads(path.read_text(encoding="utf-8")))

    def list_sessions(self):
        result = []
        for path in sorted(self.directory.glob("work_*.json"), reverse=True):
            try:
                data = self.read(path)
                result.append({"path": path, "metadata": data["metadata"], "saved_at": data["saved_at"]})
            except (OSError, ValueError, TypeError):
                continue
        return result
