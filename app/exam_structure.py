"""Read an exam paper locally and pull out its item structure (번호, 유형, 배점, 보기 수).

Only the structure is used, and nothing is sent anywhere. HWPX and PDF are read
with built-in code; HWP (binary) needs the local ``kordoc`` CLI, which is run
without any of its network-using options (formula OCR model download, webhooks).
The teacher confirms the result before it is used.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SUPPORTED_SUFFIXES = (".hwp", ".hwpx", ".pdf", ".txt", ".md")
CHOICE_MARKS = "①②③④⑤⑥"
_WINDOWS_SHELL_CHARS = set('&|<>^%!"')

_SERDAP_WORDS = "서답형|서술형|논술형|단답형"
_SECTION = re.compile(  # a heading line such as "[서답형]" or "선택형 문항"
    rf"^\s*[\[\(<【〈《]?\s*(선택형|{_SERDAP_WORDS})\s*(?:문항|문제)?\s*[\]\)>】〉》]?\s*$"
)
_SERDAP_HEADER = re.compile(  # "[서답형 1]", "서술형 2.", "[서답형 1-2]"; not a range such as "서답형 1~2번은"
    rf"^\s*[\[\(<【〈《]?\s*(?:{_SERDAP_WORDS})\s*[-–]?\s*(\d{{1,2}})(?:\s*번)?(?:\s*[-–]\s*(\d{{1,2}}))?(?!\d)(?!\s*[~∼]\s*\d)"
)
_SELECT_HEADER = re.compile(r"^\s*(?:문항?\s*)?(?:\[\s*(\d{1,2})\s*\]|(\d{1,2})\s*번?\s*([.)．]))")
_POINTS = re.compile(
    r"[\[\(〔［<〈【]\s*(?:배점\s*[:：]?\s*)?(\d{1,2}(?:\.\d{1,2})?)\s*점\s*[\]\)〕］>〉】]"
    r"|배점\s*[:：]?\s*(\d{1,2}(?:\.\d{1,2})?)"
    r"|(?<![\d.])(\d{1,2}(?:\.\d{1,2})?)\s*점\s*$"
)
_PAREN_CHOICES = [f"({k})" for k in range(1, 6)]
_DECLARED = re.compile(r"(선택형|서답형|서술형|논술형)\s*(?:\d{1,2}\s*[~∼\-–]\s*)?(\d{1,2})\s*(?:번|문항)")
_MAX_SKIP = 2  # a header may skip at most this many numbers (e.g. a lost line in a PDF)


class ExamReadError(ValueError):
    pass


# --------------------------------------------------------------------------- 읽기

def find_kordoc() -> str:
    """Finder- or Explorer-launched apps get a minimal PATH, so also look in usual install folders."""
    found = shutil.which("kordoc")
    if found:
        return found
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", "")
        candidates = [Path(base) / "npm" / "kordoc.cmd"] if base else []
    else:
        candidates = [Path("/opt/homebrew/bin/kordoc"), Path("/usr/local/bin/kordoc"), Path.home() / ".local/bin/kordoc"]
    return next((str(path) for path in candidates if path.is_file()), "")


def _xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraph_text(element) -> str:
    """Text of one paragraph without the paragraphs nested inside it (tables, text boxes)."""
    chunks = []
    for child in element:
        tag = _xml_name(child.tag)
        if tag == "p":
            continue  # read on its own
        if tag == "t":
            chunks.append(child.text or "")
            for part in child:  # <hp:t>앞<hp:lineBreak/>뒤</hp:t>
                chunks.append("\n" if _xml_name(part.tag) in {"lineBreak", "br"} else "")
                chunks.append(part.tail or "")
        elif tag in {"lineBreak", "br"}:
            chunks.append("\n")
        else:
            chunks.append(_paragraph_text(child))
    return "".join(chunks)


def _read_hwpx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            sections = sorted(
                name for name in archive.namelist()
                if name.lower().startswith("contents/") and "section" in name.lower() and name.lower().endswith(".xml")
            )
            lines = []
            for name in sections:
                root = ET.fromstring(archive.read(name))
                for para in root.iter():
                    if _xml_name(para.tag) == "p":
                        text = _paragraph_text(para).strip()
                        if text:
                            lines.append(text)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError) as exc:
        raise ExamReadError("HWPX 파일 구조를 읽지 못했습니다.") from exc
    return "\n".join(lines)


def _read_pdf(path: Path) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ExamReadError("PDF를 열지 못했습니다. 손상되었거나 암호가 걸린 파일인지 확인하세요.") from exc


def _read_with_kordoc(path: Path, kordoc: str) -> str:
    # On Windows kordoc.cmd runs through cmd.exe, which would interpret & | % and similar
    # characters in a file name. Hand it a copy under a fixed, safe name instead.
    with tempfile.TemporaryDirectory(prefix="goedu-exam-") as folder:
        safe = Path(folder) / ("input" + path.suffix.lower())
        if sys.platform.startswith("win") and _WINDOWS_SHELL_CHARS & set(str(safe)):
            raise ExamReadError("임시 폴더 경로에 특수문자가 있어 kordoc을 안전하게 실행할 수 없습니다. HWPX나 PDF로 저장해 불러오세요.")
        try:
            shutil.copyfile(path, safe)
            completed = subprocess.run(
                [kordoc, str(safe), "--silent"], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=90, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExamReadError("kordoc을 실행하지 못했거나 시간이 너무 오래 걸렸습니다.") from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ExamReadError("kordoc이 이 파일을 읽지 못했습니다.")
    return markdown_to_lines(completed.stdout)


def markdown_to_lines(markdown: str) -> str:
    """Undo Markdown escapes and put each table cell on its own line (exam papers often use tables)."""
    lines = []
    for line in markdown.splitlines():
        line = re.sub(r"\\([\\`*_{}\[\]()#+\-.!~|>])", r"\1", line)
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) or not cell for cell in cells):
                continue
            lines.extend(cell for cell in cells if cell)
        else:
            lines.append(line)
    return "\n".join(lines)


def extract_exam_text(path: str | Path) -> tuple[str, str]:
    """Return (text, how it was read)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ExamReadError("HWP, HWPX, PDF, TXT 파일만 읽을 수 있습니다.")
    if not path.is_file():
        raise ExamReadError("파일을 찾을 수 없습니다.")
    try:
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="replace"), "텍스트"
    except OSError as exc:
        raise ExamReadError("파일을 열 수 없습니다. 권한을 확인하세요.") from exc
    if suffix == ".hwpx":
        text, how = _read_hwpx(path), "HWPX 내장 읽기"
    elif suffix == ".pdf":
        text, how = _read_pdf(path), "PDF 내장 읽기"
    else:
        text, how = "", ""
    if not text.strip():
        kordoc = find_kordoc()
        if not kordoc:
            raise ExamReadError(
                "HWP 파일은 이 PC에 kordoc이 설치되어 있어야 읽을 수 있습니다. 한글에서 HWPX나 PDF로 저장해 불러오세요."
                if suffix == ".hwp" else "파일에서 글자를 찾지 못했습니다. 스캔한(그림) PDF는 읽을 수 없습니다."
            )
        text, how = _read_with_kordoc(path, kordoc), "kordoc(이 PC)"
    return text, how


# --------------------------------------------------------------------------- 구조

def _points_in(text: str) -> list[float]:
    values = []
    for line in text.split("\n"):
        values += [float(a or b or c) for a, b, c in _POINTS.findall(line)]
    return values


def _count_choices(block: str) -> int:
    circled = len({mark for mark in CHOICE_MARKS if mark in block})
    return circled or sum(1 for mark in _PAREN_CHOICES if mark in block)


def _candidates(lines: list[str]) -> list[tuple[int, str, int, int | None, bool]]:
    """(line, kind, number, sub-number, explicit label) for every line that looks like an item header."""
    found, section = [], "선택형"
    for index, line in enumerate(lines):
        if not line:
            continue
        heading = _SECTION.match(line)
        if heading:
            section = "선택형" if heading.group(1) == "선택형" else "서답형"
            continue
        serdap = _SERDAP_HEADER.match(line)
        if serdap:
            sub = int(serdap.group(2)) if serdap.group(2) else None
            found.append((index, "서답형", int(serdap.group(1)), sub, True))
            continue
        select = _SELECT_HEADER.match(line)
        if not select:
            continue
        number = int(select.group(1) or select.group(2))
        if select.group(3) == ")" and not _points_in(line):
            continue  # "2) 조건" inside an item; "3) ... [4점]" is still a header
        found.append((index, section, number, None, False))
    return found


def parse_exam_structure(text: str) -> dict:
    """Find item headers in reading order and read 배점 and choices from each item's block."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    candidates = _candidates(lines)
    headers = []  # (line, kind, number, note, has sub-items)
    expected = {"선택형": 1, "서답형": 1}
    serdap_offset = None
    for position, (index, kind, number, sub, labelled) in enumerate(candidates):
        nxt = candidates[position + 1][0] if position + 1 < len(candidates) else len(lines)
        block = "\n".join(lines[index:nxt])
        if not labelled and not (_points_in(block) or _count_choices(block)):
            continue  # numbered notes on the cover page have neither 배점 nor choices
        note = ""
        if kind == "서답형":
            if serdap_offset is None:
                last_select = expected["선택형"] - 1
                serdap_offset = number - 1 if number > 1 and last_select and number - last_select in (1, 2, 3) else 0
                if serdap_offset:
                    note = f"시험지 번호 {number}번을 서답형 1번부터 다시 매겼습니다."
            number -= serdap_offset
            if sub is not None and headers and headers[-1][1] == "서답형" and headers[-1][2] == number:
                continue  # [서답형 1-2] belongs to 서답형 1
        if expected[kind] <= number <= expected[kind] + _MAX_SKIP:
            headers.append((index, kind, number, note, sub is not None))
            expected[kind] = number + 1

    items = []
    for position, (start, kind, number, note, has_parts) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        block = "\n".join(lines[start:end])
        header_points = _points_in(lines[start])
        block_points = _points_in(block)
        flags = [note] if note else []
        if has_parts and len(block_points) > 1:
            points = sum(block_points)
            flags.append(f"소문항 배점을 합했습니다({' + '.join(f'{p:g}' for p in block_points)}).")
        elif header_points:
            points = header_points[0]
        elif len(block_points) == 1:
            points = block_points[0]
        elif block_points:
            points = sum(block_points)
            flags.append(f"배점이 여러 곳에 있어 합했습니다({' + '.join(f'{p:g}' for p in block_points)}).")
        else:
            points = None
            flags.append("배점을 찾지 못했습니다.")
        choices = _count_choices(block) if kind == "선택형" else len({m for m in CHOICE_MARKS if m in block})
        if kind == "선택형" and choices == 0:
            flags.append("보기(①~⑤)를 찾지 못했습니다.")
        items.append({
            "type": kind, "number": number, "points": points, "choices": choices, "flags": flags,
            "preview": re.sub(r"\s+", " ", lines[start])[:40],
        })

    warnings = []
    declared = {}
    for word, last in _DECLARED.findall(text):
        kind = "선택형" if word == "선택형" else "서답형"
        declared[kind] = max(declared.get(kind, 0), int(last))
    for kind in ("선택형", "서답형"):
        numbers = [item["number"] for item in items if item["type"] == kind]
        top = max(numbers + [declared.get(kind, 0)]) if (numbers or kind in declared) else 0
        missing = sorted(set(range(1, top + 1)) - set(numbers))
        if missing:
            warnings.append(f"{kind} {', '.join(map(str, missing))}번을 찾지 못했습니다.")
    total = sum(item["points"] for item in items if item["points"] is not None)
    if not items:
        warnings.append("문항 번호를 찾지 못했습니다. '1.' 또는 '[서답형 1]' 형식인지 확인하세요.")
    elif any(item["points"] is None for item in items):
        warnings.append("배점을 찾지 못한 문항이 있습니다. 표에서 직접 입력하세요.")
    elif abs(total - 100) > 1e-6:
        warnings.append(f"배점 합계가 {total:g}점입니다. 시험 총점과 같은지 확인하세요.")
    return {"items": items, "warnings": warnings, "total_points": total}


def designs_from_structure(rows: list[dict], rates: dict[str, float], difficulty: str = "보통", target: str = "C") -> list[dict]:
    """Calculator items for the confirmed rows. Every row needs 배점 greater than 0."""
    designs = []
    for row in rows:
        points = row.get("points")
        if points is None or not float(points) > 0:
            raise ValueError(f"{row['type']} {row['number']}번의 배점을 입력해 주세요.")
        designs.append({
            "number": int(row["number"]), "type": row["type"], "points": float(points),
            "difficulty": difficulty, "target": target, "rates": dict(rates), "sampleSize": 20,
        })
    return designs
