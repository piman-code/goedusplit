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
_POINTS = re.compile(  # "[3점]", "(3.5점)", "<4점>", "【3점】", "[배점 3점]", "배점: 4"
    r"[\[\(〔［<〈【]\s*(?:배점\s*[:：]?\s*)?(\d{1,2}(?:\.\d{1,2})?)(?![\d.])\s*점\s*[\]\)〕］>〉】]"
    r"|배점\s*[:：]?\s*(\d{1,2}(?:\.\d{1,2})?)(?![\d.])"
)
_BARE_POINTS = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d{1,2})?)\s*점\s*$")  # "… 4점" at a line end: weaker
_PAREN_CHOICES = [f"({k})" for k in range(1, 6)]
_DECLARED = re.compile(  # "선택형 1~20번", "서답형 2문항" on the cover
    r"(선택형|서답형|서술형|논술형)\s*(?:\d{1,2}\s*[~∼\-–]\s*(\d{1,2})\s*번|(\d{1,2})\s*문항)"
)
_MAX_SKIP = 2  # a header may skip at most this many numbers (e.g. a lost line in a PDF)
_RUBRIC_START = re.compile(r"채점\s*기준")  # 논술형 채점 기준표 after the questions
_RUBRIC_HEADER = re.compile(rf"^\s*(?:{_SERDAP_WORDS})\s*(\d{{1,2}})\s*$")
_NUMBER_ONLY = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2})?)\s*$")
_CHOICE_LINE = re.compile(r"^\s*[①②③④⑤⑥]")
_AUTO_NUMBER_NOTE = "시험지에 문항 번호 글자가 없어(한글 자동 번호) 보기(①~⑤) 순서로 번호를 매겼습니다. 문항 수와 순서를 확인하세요."


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


KORDOC_TIMEOUT = 90


def _kill_process_tree(process: subprocess.Popen) -> None:
    """kordoc.cmd starts node under cmd.exe; killing only cmd.exe leaves node holding the pipes."""
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, 9)
        except OSError:
            process.kill()


def _kordoc_env(kordoc: str) -> dict:
    """kordoc is a Node script ("#!/usr/bin/env node"). An app opened from Finder gets a PATH without
    Homebrew, so node was not found and every HWP failed in the installed app; add kordoc's own folder
    (where npm put node's link) and the usual install folders."""
    env = dict(os.environ)
    if sys.platform.startswith("win"):
        return env
    extra = [str(Path(kordoc).parent), "/opt/homebrew/bin", "/usr/local/bin"]
    current = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    env["PATH"] = os.pathsep.join(dict.fromkeys(extra + current))
    return env


def _read_with_kordoc(path: Path, kordoc: str) -> str:
    # On Windows kordoc.cmd runs through cmd.exe, which would interpret & | % and similar
    # characters in a file name. Hand it a copy under a fixed, safe name instead.
    with tempfile.TemporaryDirectory(prefix="goedu-exam-", ignore_cleanup_errors=True) as folder:
        safe = Path(folder) / ("input" + path.suffix.lower())
        if sys.platform.startswith("win") and _WINDOWS_SHELL_CHARS & set(str(safe)):
            raise ExamReadError("임시 폴더 경로에 특수문자가 있어 kordoc을 안전하게 실행할 수 없습니다. HWPX나 PDF로 저장해 불러오세요.")
        try:
            shutil.copyfile(path, safe)
        except OSError as exc:
            raise ExamReadError("시험지를 임시 폴더로 복사하지 못했습니다.") from exc
        group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform.startswith("win") else {"start_new_session": True}
        try:
            process = subprocess.Popen(
                [kordoc, str(safe), "--silent"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=_kordoc_env(kordoc), **group,
            )
        except OSError as exc:
            raise ExamReadError("kordoc을 실행하지 못했습니다.") from exc
        try:
            stdout, stderr = process.communicate(timeout=KORDOC_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            _kill_process_tree(process)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            raise ExamReadError("kordoc이 너무 오래 걸려 중단했습니다. HWPX나 PDF로 저장해 불러오세요.") from exc
    if process.returncode != 0 and "node" in (stderr or "") and "No such file" in (stderr or ""):
        raise ExamReadError("kordoc을 실행할 Node.js를 찾지 못했습니다. Node.js를 설치하거나 HWPX·PDF로 저장해 불러오세요.")
    if process.returncode != 0 or not (stdout or "").strip():
        raise ExamReadError("kordoc이 이 파일을 읽지 못했습니다.")
    return markdown_to_lines(stdout)


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
    """배점 written in brackets or after the word 배점."""
    values = []
    for line in text.split("\n"):
        values += [float(a or b) for a, b in _POINTS.findall(line)]
    return values


def _bare_points_in(text: str) -> list[float]:
    return [float(match.group(1)) for line in text.split("\n") if (match := _BARE_POINTS.search(line))]


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


def _item_points(block: str, header_line: str, has_parts: bool = False) -> tuple[float | None, list[str]]:
    header_points = _points_in(header_line)
    block_points = _points_in(block)
    bare_points = _bare_points_in(block)
    if has_parts and len(block_points) > 1:
        return sum(block_points), [f"소문항 배점을 합했습니다({' + '.join(f'{p:g}' for p in block_points)})."]
    if header_points:
        return header_points[0], []
    if len(block_points) == 1:
        return block_points[0], []
    if block_points:
        return sum(block_points), [f"배점이 여러 곳에 있어 합했습니다({' + '.join(f'{p:g}' for p in block_points)})."]
    if len(bare_points) == 1:
        return bare_points[0], [f"괄호 없는 '{bare_points[0]:g}점'을 배점으로 읽었습니다. 확인하세요."]
    return None, ["배점을 찾지 못했습니다."]


def _rubric_points(lines: list[str], start: int) -> dict[int, float]:
    """배점 of each 논술형 from the 채점 기준표: in each item's block the second number-only line.

    The first is the score of the first step, the second the item's 배점 (e.g. 1.0 then 5.0).
    """
    result, current, numbers = {}, None, []
    for line in lines[start:] + ["논술형 99"]:
        header = _RUBRIC_HEADER.match(line)
        if header:
            if current is not None and len(numbers) >= 2:
                result[current] = numbers[1]
            current, numbers = int(header.group(1)), []
            continue
        number = _NUMBER_ONLY.match(line)
        if current is not None and number:
            numbers.append(float(number.group(1)))
    return result


def _parse_by_choices(lines: list[str], serdap_expected: int) -> list[dict]:
    """For papers whose item numbers are HWP auto numbers (not in the text): one 선택형 per ① group."""
    cutoff = next((i for i, line in enumerate(lines) if _RUBRIC_START.search(line)), len(lines))
    groups = []  # (first choice line, last choice line)
    index = 0
    while index < cutoff:
        if lines[index].startswith("①"):
            end, look = index, index + 1
            while look < cutoff and (not lines[look] or _CHOICE_LINE.match(lines[look])):
                if lines[look]:
                    end = look  # choices may be split over lines with blank lines between them
                look += 1
            groups.append((index, end))
            index = end + 1
        else:
            index += 1
    items, previous_end = [], -1
    for number, (first, last) in enumerate(groups, start=1):
        question = [line for line in lines[previous_end + 1:first] if line]
        block = "\n".join(question)
        points, flags = _item_points(block, question[-1] if question else "")
        choices = len({mark for mark in CHOICE_MARKS if mark in "\n".join(lines[first:last + 1])})
        items.append({"type": "선택형", "number": number, "points": points, "choices": choices, "flags": flags,
                      "preview": re.sub(r"\s+", " ", question[-1] if question else "")[:40]})
        previous_end = last
    rest = [line for line in lines[previous_end + 1:cutoff]
            if len(line) >= 15 and not line.startswith(("<", "○", "※", "(", "[", "①")) and not _CHOICE_LINE.match(line)]
    rubric = _rubric_points(lines, cutoff)
    for number, line in enumerate(rest[:serdap_expected] if serdap_expected else rest, start=1):
        points = rubric.get(number)
        flags = ["채점 기준표에서 배점을 읽었습니다. 확인하세요."] if points is not None else ["배점을 찾지 못했습니다."]
        items.append({"type": "서답형", "number": number, "points": points, "choices": 0, "flags": flags,
                      "preview": re.sub(r"\s+", " ", line)[:40]})
    return items


def _declared_counts(text: str) -> dict[str, int]:
    declared = {}
    for word, last_of_range, count in _DECLARED.findall(text):
        kind = "선택형" if word == "선택형" else "서답형"
        declared[kind] = max(declared.get(kind, 0), int(last_of_range or count))
    return declared


def parse_exam_structure(text: str) -> dict:
    """Numbered items when the text has item numbers; otherwise items by choice groups (HWP auto numbers)."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    numbered = _parse_numbered(lines, text)
    numbered_select = sum(1 for item in numbered["items"] if item["type"] == "선택형")
    cutoff = next((i for i, line in enumerate(lines) if _RUBRIC_START.search(line)), len(lines))
    group_count = sum(1 for line in lines[:cutoff] if line.startswith("①"))
    if group_count >= 2 and group_count > numbered_select * 1.5:
        declared = _declared_counts("\n".join(lines[:cutoff]))
        items = _parse_by_choices(lines, declared.get("서답형", 0))
        return _finish(items, declared, extra_warnings=[_AUTO_NUMBER_NOTE])
    return numbered


def _parse_numbered(lines: list[str], text: str) -> dict:
    """Find item headers in reading order and read 배점 and choices from each item's block."""
    candidates = _candidates(lines)
    headers = []  # (line, kind, number, note, has sub-items)
    expected = {"선택형": 1, "서답형": 1}
    serdap_offset = None
    for position, (index, kind, number, sub, labelled) in enumerate(candidates):
        nxt = candidates[position + 1][0] if position + 1 < len(candidates) else len(lines)
        block = "\n".join(lines[index:nxt])
        if kind == "선택형" and not labelled and not (_points_in(block) or _count_choices(block)):
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
        points, point_flags = _item_points(block, lines[start], has_parts)
        flags = ([note] if note else []) + point_flags
        choices = _count_choices(block) if kind == "선택형" else len({m for m in CHOICE_MARKS if m in block})
        if kind == "선택형" and choices == 0:
            flags.append("보기(①~⑤)를 찾지 못했습니다.")
        items.append({
            "type": kind, "number": number, "points": points, "choices": choices, "flags": flags,
            "preview": re.sub(r"\s+", " ", lines[start])[:40],
        })

    cover = "\n".join(lines[:headers[0][0]]) if headers else text  # only the part before the first item
    declared = _declared_counts(cover)
    if serdap_offset and declared.get("서답형", 0) > serdap_offset:
        declared["서답형"] -= serdap_offset
    return _finish(items, declared)


def _finish(items: list[dict], declared: dict[str, int], extra_warnings: list[str] | None = None) -> dict:
    warnings = list(extra_warnings or [])
    missing = [item for item in items if item["points"] is None]
    known = sum(item["points"] for item in items if item["points"] is not None)
    if len(missing) == 1 and len(items) > 1 and 0 < 100 - known <= 20:
        # School written exams total 100 points; one gap is usually a 배점 the text lost.
        item = missing[0]
        item["points"] = round(100 - known, 2)
        item["flags"] = [flag for flag in item["flags"] if flag != "배점을 찾지 못했습니다."]
        item["flags"].append(f"배점을 찾지 못해 총점 100점에서 나머지({item['points']:g}점)로 채웠습니다. 확인하세요.")
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


def designs_from_structure(rows: list[dict], rates_for) -> list[dict]:
    """Calculator items for the confirmed rows. Every row needs 배점 greater than 0.

    ``rates_for(target, difficulty)`` gives the default A~E rates (the app's preset table).
    """
    designs = []
    for row in rows:
        points = row.get("points")
        if points is None or not float(points) > 0:
            raise ValueError(f"{row['type']} {row['number']}번의 배점을 입력해 주세요.")
        difficulty = row.get("difficulty") if row.get("difficulty") in DIFFICULTIES else "보통"
        target = row.get("target") if row.get("target") in ("A", "B", "C", "D", "E") else "C"
        designs.append({
            "number": int(row["number"]), "type": row["type"], "points": float(points),
            "difficulty": difficulty, "target": target, "standard": row.get("standard", ""),
            "rates": dict(rates_for(target, difficulty)), "sampleSize": 20,
        })
    return designs


DIFFICULTIES = ("쉬움", "보통", "어려움")


def enrich_structure(items: list[dict], item_info: list | None) -> tuple[list[dict], str]:
    """Add 난이도 (and 성취기준) to each item: from the NEIS 문항정보표 when given, else estimated.

    ``item_info`` holds objects with item_type, number, difficulty, score, standard_code, standard.
    The table is used only when its 배점 match this paper for at least 80% of the items that
    have 배점, since the table chosen in the app may belong to an earlier exam.
    Returns (rows, where the 난이도 came from: "문항정보표", "문항정보표 불일치" or "배점 순서로 추정").
    """
    rows = [dict(item, flags=list(item["flags"]), difficulty="보통", standard="") for item in items]
    source = "배점 순서로 추정"
    if item_info:
        by_key = {(info.item_type, int(info.number)): info for info in item_info}
        scored = [row for row in rows if row["points"] is not None]
        agree = sum(1 for row in scored if (row["type"], row["number"]) in by_key
                    and abs(float(by_key[(row["type"], row["number"])].score or 0) - row["points"]) < 1e-6)
        if scored and agree / len(scored) < 0.8:
            item_info, source = None, "문항정보표 불일치"
    if item_info:
        for row in rows:
            info = by_key.get((row["type"], row["number"]))
            if info is None:
                row["flags"].append("문항정보표에 없는 문항입니다.")
                continue
            row["difficulty"] = info.difficulty if info.difficulty in DIFFICULTIES else "보통"
            row["standard"] = f"{info.standard_code} {info.standard}".strip()
            score = float(info.score or 0)
            if score > 0 and row["points"] is None:
                row["points"] = score
                row["flags"] = [flag for flag in row["flags"] if flag != "배점을 찾지 못했습니다."]
                row["flags"].append("문항정보표 배점으로 채웠습니다.")
            elif score > 0 and abs(row["points"] - score) > 1e-6:
                row["flags"].append(f"문항정보표 배점은 {score:g}점입니다. 확인하세요.")
        return rows, "문항정보표"
    # Without the table, higher 배점 usually means a harder item: split each type into thirds by 배점.
    for kind in ("선택형", "서답형"):
        scored = sorted((row for row in rows if row["type"] == kind and row["points"] is not None), key=lambda r: r["points"])
        values = [row["points"] for row in scored]
        if len(set(values)) < 2:
            continue
        third = len(values) // 3  # lowest third 쉬움, highest third 어려움, the rest 보통
        low, high = values[max(0, third - 1)], values[min(len(values) - 1, len(values) - max(third, 1))]
        for row in scored:
            if low < high and row["points"] <= low:
                row["difficulty"] = "쉬움"
            elif low < high and row["points"] >= high:
                row["difficulty"] = "어려움"
    return rows, source
