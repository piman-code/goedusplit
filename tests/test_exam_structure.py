import os
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.exam_structure import (
    ExamReadError, designs_from_structure, enrich_structure, extract_exam_text, find_kordoc, markdown_to_lines,
    parse_exam_structure,
)
from types import SimpleNamespace

try:
    from app.main_window import MainWindow
except ModuleNotFoundError:
    MainWindow = None

PAPER = """2026학년도 1학기 1차 지필평가 수학 (합성 예시)
※ 선택형 1~4번, 서답형 1~2번
서답형 1~2번은 풀이 과정을 쓰시오.
1. 두 다항식 A, B에 대하여 A+B는? [3.5점]
2) 조건: 이 줄은 1번 문항 안의 조건이다.
① 가 ② 나 ③ 다 ④ 라 ⑤ 마
2. 다음 중 옳은 것은? (4점)
① 가 ② 나 ③ 다 ④ 라 ⑤ 마
3) x=2일 때 식의 값은? [4.5점]
① 1 ② 2 ③ 3 ④ 4 ⑤ 5
4. 다음을 계산하면? [5점]
① 10 ② 20 ③ 30 ④ 40 ⑤ 50
[서답형 1] 두 근을 구하는 과정을 쓰시오. [6점]
[서답형 2] 다음 물음에 답하시오.
(1) 첫째 물음 [3점]
(2) 둘째 물음 [4점]"""


def _summary(result):
    return [(i["type"], i["number"], i["points"], i["choices"]) for i in result["items"]]


def _hwpx(path: Path, text: str):
    ns = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
    paras = "".join(
        f"<hp:p><hp:run><hp:t>{line.replace('&', '&amp;').replace('<', '&lt;')}</hp:t></hp:run></hp:p>"
        for line in text.split("\n")
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("Contents/section0.xml", f'<?xml version="1.0" encoding="UTF-8"?><hs:sec {ns}>{paras}</hs:sec>')


EXPECTED = [("선택형", 1, 3.5, 5), ("선택형", 2, 4.0, 5), ("선택형", 3, 4.5, 5), ("선택형", 4, 5.0, 5),
            ("서답형", 1, 6.0, 0), ("서답형", 2, 7.0, 0)]


class ExamStructureParseTests(unittest.TestCase):
    def test_reads_items_points_and_choices_and_avoids_false_headers(self):
        result = parse_exam_structure(PAPER)
        self.assertEqual(_summary(result), EXPECTED)
        self.assertEqual(result["total_points"], 30.0)
        self.assertEqual(result["warnings"], ["배점 합계가 30점입니다. 시험 총점과 같은지 확인하세요."])
        serdap2 = result["items"][-1]
        self.assertIn("합했습니다(3 + 4)", serdap2["flags"][0])
        self.assertTrue(result["items"][0]["preview"].startswith("1. 두 다항식"))

    def test_missing_numbers_points_and_choices_are_reported(self):
        text = "1. 첫 문항 [5점]\n① 가 ② 나\n2. 둘째 문항\n① 가\n4. 넷째 문항 [5점]\n보기 없음"
        result = parse_exam_structure(text)
        self.assertEqual([(i["number"], i["points"]) for i in result["items"]], [(1, 5.0), (2, None), (4, 5.0)])
        self.assertIn("선택형 3번을 찾지 못했습니다.", result["warnings"])
        self.assertIn("배점을 찾지 못한 문항이 있습니다. 표에서 직접 입력하세요.", result["warnings"])
        self.assertIn("보기(①~⑤)를 찾지 못했습니다.", result["items"][2]["flags"])

    def test_numbers_far_ahead_are_not_headers(self):
        # "10." 은 다음 기대 번호(2)에서 너무 멀어 문항 머리로 보지 않는다
        result = parse_exam_structure("1. 첫 문항 [5점]\n① 가\n10. 이 줄은 보기 설명\n2. 둘째 [5점]\n① 가")
        self.assertEqual([i["number"] for i in result["items"]], [1, 2])

    def test_nothing_found_explains_expected_format(self):
        self.assertIn("문항 번호를 찾지 못했습니다", parse_exam_structure("안내문만 있음")["warnings"][0])

    def test_common_school_notations(self):
        cases = [
            ("[1] 첫 문항 [3점]\n① 가 ② 나", [("선택형", 1, 3.0)]),
            ("문 1. 첫 문항 (3점)\n① 가", [("선택형", 1, 3.0)]),
            ("1번. 첫 문항 <4점>\n① 가", [("선택형", 1, 4.0)]),
            ("1. 첫 문항 【3.5점】\n① 가", [("선택형", 1, 3.5)]),
            ("1. 첫 문항의 값을 구하면? 4점\n① 가", [("선택형", 1, 4.0)]),
            ("1. 첫 문항 [배점 3점]\n(1) 가 (2) 나 (3) 다 (4) 라 (5) 마", [("선택형", 1, 3.0)]),
        ]
        for text, expected in cases:
            with self.subTest(text=text.split("\n")[0]):
                result = parse_exam_structure(text)
                self.assertEqual([(i["type"], i["number"], i["points"]) for i in result["items"]], expected)
        self.assertEqual(parse_exam_structure(cases[-1][0])["items"][0]["choices"], 5)

    def test_bare_points_do_not_override_bracketed_points(self):
        text = "1. 어느 반 학생 5명의 평균 점수가 72점\n일 때 옳은 것은? [4점]\n① 가 ② 나"
        item = parse_exam_structure(text)["items"][0]
        self.assertEqual((item["points"], item["flags"]), (4.0, []))
        bare = parse_exam_structure("1. 다음 값은? 4점\n① 가")["items"][0]
        self.assertEqual(bare["points"], 4.0)
        self.assertIn("괄호 없는 '4점'을 배점으로 읽었습니다. 확인하세요.", bare["flags"])
        self.assertIsNone(parse_exam_structure("1. 배점: 100\n① 가")["items"][0]["points"])  # 10점으로 읽지 않는다

    def test_serdap_heading_keeps_items_without_points(self):
        text = "1. 첫 [3점]\n① 가\n[서답형]\n1. 과정을 쓰시오.\n2. 설명하시오. [6점]"
        result = parse_exam_structure(text)
        self.assertEqual([(i["type"], i["number"], i["points"]) for i in result["items"]],
                         [("선택형", 1, 3.0), ("서답형", 1, None), ("서답형", 2, 6.0)])

    def test_declared_counts_come_from_the_cover_only(self):
        continued = "1. 첫 [3점]\n① 가\n2. 둘째 [3점]\n① 가\n[서답형 3번] 과정 [5점]\n[서답형 4번] 설명. 서술형 3문항 중 [6점]"
        self.assertEqual(parse_exam_structure(continued)["warnings"], ["배점 합계가 17점입니다. 시험 총점과 같은지 확인하세요."])

    def test_cover_page_notes_are_not_items(self):
        text = ("유의사항\n1. 답안지에 이름을 쓰시오.\n2. 시간은 50분입니다.\n3. 휴대전화를 끄시오.\n"
                "1. 첫 문항 [3점]\n① 가 ② 나\n2. 둘째 문항 [4점]\n① 가 ② 나")
        result = parse_exam_structure(text)
        self.assertEqual([(i["number"], i["points"]) for i in result["items"]], [(1, 3.0), (2, 4.0)])

    def test_serdap_section_heading_parts_and_continued_numbers(self):
        heading = "1. 첫 문항 [3점]\n① 가\n[서답형]\n1. 과정을 쓰시오. [5점]\n2. 설명하시오. [6점]"
        self.assertEqual([(i["type"], i["number"], i["points"]) for i in parse_exam_structure(heading)["items"]],
                         [("선택형", 1, 3.0), ("서답형", 1, 5.0), ("서답형", 2, 6.0)])
        parts = "[서답형 1-1] 앞 [2점]\n[서답형 1-2] 뒤 [3점]\n[서답형 2] 다음 [5점]"
        result = parse_exam_structure(parts)
        self.assertEqual([(i["number"], i["points"]) for i in result["items"]], [(1, 5.0), (2, 5.0)])
        self.assertIn("소문항 배점을 합했습니다(2 + 3).", result["items"][0]["flags"])
        continued = "1. 첫 [3점]\n① 가\n2. 둘째 [3점]\n① 가\n[서답형 3] 과정 [5점]\n[서답형 4] 설명 [6점]"
        result = parse_exam_structure(continued)
        self.assertEqual([(i["type"], i["number"]) for i in result["items"]],
                         [("선택형", 1), ("선택형", 2), ("서답형", 1), ("서답형", 2)])
        self.assertIn("시험지 번호 3번을 서답형 1번부터 다시 매겼습니다.", result["items"][2]["flags"])

    def test_declared_count_reveals_missing_last_items(self):
        text = "※ 선택형 1~5번, 서답형 1~2번\n1. 첫 [5점]\n① 가\n2. 둘째 [5점]\n① 가\n3. 셋째 [5점]\n① 가\n[서답형 1] 과정 [5점]"
        warnings = parse_exam_structure(text)["warnings"]
        self.assertIn("선택형 4, 5번을 찾지 못했습니다.", warnings)
        self.assertIn("서답형 2번을 찾지 못했습니다.", warnings)

    def test_markdown_tables_and_escapes_become_lines(self):
        text = markdown_to_lines("※ 1\\~4번\n| 1\\. 문제 [3점] | ① 가 ② 나 |\n| --- | --- |\n| 2. 다음 (4점) | ① 가 |")
        self.assertEqual(text.split("\n"), ["※ 1~4번", "1. 문제 [3점]", "① 가 ② 나", "2. 다음 (4점)", "① 가"])


class ExamReadTests(unittest.TestCase):
    def test_hwpx_and_text_files_give_the_same_structure(self):
        with TemporaryDirectory() as directory:
            hwpx = Path(directory) / "paper.hwpx"
            _hwpx(hwpx, PAPER)
            text, how = extract_exam_text(hwpx)
            self.assertEqual(how, "HWPX 내장 읽기")
            self.assertEqual(_summary(parse_exam_structure(text)), EXPECTED)
            txt = Path(directory) / "paper.txt"
            txt.write_text(PAPER, encoding="utf-8")
            self.assertEqual(_summary(parse_exam_structure(extract_exam_text(txt)[0])), EXPECTED)

    def test_hwpx_table_paragraphs_are_read_once_and_separately(self):
        ns = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        inner = "".join(f"<hp:tc><hp:subList><hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
                        for text in ("1. 첫 문항", "① 가 ② 나", "2. 둘째 문항 [4점]", "① 가"))
        section = (f'<?xml version="1.0" encoding="UTF-8"?><hs:sec {ns}><hp:p><hp:run><hp:t>표 앞 글</hp:t>'
                   f"<hp:tbl><hp:tr>{inner}</hp:tr></hp:tbl></hp:run></hp:p>"
                   "<hp:p><hp:run><hp:t>줄<hp:lineBreak/>바꿈</hp:t></hp:run></hp:p></hs:sec>")
        with TemporaryDirectory() as directory:
            hwpx = Path(directory) / "table.hwpx"
            with zipfile.ZipFile(hwpx, "w") as archive:
                archive.writestr("Contents/section0.xml", section)
            text, _ = extract_exam_text(hwpx)
        self.assertEqual(text.split("\n"), ["표 앞 글", "1. 첫 문항", "① 가 ② 나", "2. 둘째 문항 [4점]", "① 가", "줄", "바꿈"])
        items = parse_exam_structure(text)["items"]
        self.assertEqual([(i["number"], i["points"]) for i in items], [(1, None), (2, 4.0)])  # 2번 배점이 1번으로 가지 않는다

    def test_pdf_with_korean_text(self):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import font_manager, pyplot
        font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NanumGothic.ttf"
        with TemporaryDirectory() as directory, matplotlib.rc_context({"pdf.fonttype": 42}):
            pdf = Path(directory) / "paper.pdf"
            figure = pyplot.figure(figsize=(8.27, 11.69))
            figure.text(0.05, 0.95, PAPER, va="top", fontproperties=font_manager.FontProperties(fname=str(font)), fontsize=11)
            figure.savefig(pdf)
            pyplot.close(figure)
            text, how = extract_exam_text(pdf)
        self.assertEqual(how, "PDF 내장 읽기")
        self.assertEqual(_summary(parse_exam_structure(text)), EXPECTED)

    def test_hwp_without_kordoc_asks_for_hwpx_or_pdf(self):
        with TemporaryDirectory() as directory:
            hwp = Path(directory) / "paper.hwp"
            hwp.write_bytes(b"not really hwp")
            with patch("app.exam_structure.find_kordoc", return_value=""):
                with self.assertRaises(ExamReadError) as caught:
                    extract_exam_text(hwp)
        self.assertIn("HWPX나 PDF로 저장", str(caught.exception))
        with self.assertRaises(ExamReadError):
            extract_exam_text(Path("paper.docx"))

    def _fake_popen(self, calls, stdout="1\\. 문제 [5점]\n\n① 가", timeout=False):
        import subprocess

        class FakePopen:
            pid = 4321
            returncode = 0

            def __init__(self, command, **kwargs):
                copied = Path(command[1])
                calls.append((command, kwargs, copied.name, copied.read_bytes()))
                self.waits = 0

            def communicate(self, timeout=None):
                self.waits += 1
                if timeout_mode and self.waits == 1:
                    raise subprocess.TimeoutExpired("kordoc", timeout)
                return stdout, ""

        timeout_mode = timeout
        return FakePopen

    def test_kordoc_gets_a_safely_named_copy_without_shell(self):
        calls = []
        with TemporaryDirectory() as directory:
            hwp = Path(directory) / "시험 지&calc&%PATH%.hwp"
            hwp.write_bytes(b"hwp bytes")
            with patch("app.exam_structure.find_kordoc", return_value="/fake/kordoc"), \
                 patch("app.exam_structure.subprocess.Popen", self._fake_popen(calls)):
                text, how = extract_exam_text(hwp)
        command, kwargs, name, data = calls[0]
        self.assertEqual((command[0], command[2]), ("/fake/kordoc", "--silent"))
        self.assertEqual((name, data), ("input.hwp", b"hwp bytes"))  # 원래 파일명은 넘기지 않는다
        self.assertNotIn("&", command[1])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(how, "kordoc(이 PC)")
        self.assertEqual(_summary(parse_exam_structure(text)), [("선택형", 1, 5.0, 1)])

    @unittest.skipIf(sys.platform.startswith("win"), "PATH repair is for Finder-launched macOS apps")
    def test_kordoc_finds_node_when_the_app_starts_with_a_minimal_path(self):
        calls = []
        with TemporaryDirectory() as directory:
            hwp = Path(directory) / "paper.hwp"
            hwp.write_bytes(b"hwp bytes")
            with patch.dict("os.environ", {"PATH": "/usr/bin:/bin"}), \
                 patch("app.exam_structure.find_kordoc", return_value="/opt/homebrew/bin/kordoc"), \
                 patch("app.exam_structure.subprocess.Popen", self._fake_popen(calls)):
                extract_exam_text(hwp)
        path = calls[0][1]["env"]["PATH"].split(os.pathsep)
        self.assertEqual(path[0], "/opt/homebrew/bin")      # where node's link lives next to kordoc
        self.assertIn("/usr/bin", path)

    def test_kordoc_timeout_stops_the_whole_process_tree(self):
        calls = []
        with TemporaryDirectory() as directory:
            hwp = Path(directory) / "paper.hwp"
            hwp.write_bytes(b"x")
            with patch("app.exam_structure.find_kordoc", return_value="C:/npm/kordoc.cmd"), \
                 patch("app.exam_structure.sys.platform", "win32"), \
                 patch("app.exam_structure.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True), \
                 patch("app.exam_structure.subprocess.Popen", self._fake_popen(calls, timeout=True)), \
                 patch("app.exam_structure.subprocess.run") as run:
                with self.assertRaises(ExamReadError) as caught:
                    extract_exam_text(hwp)
        self.assertIn("너무 오래", str(caught.exception))
        self.assertEqual(run.call_args.args[0], ["taskkill", "/T", "/F", "/PID", "4321"])  # node 손자 프로세스까지
        self.assertEqual(calls[0][1]["creationflags"], 512)

    def test_kordoc_refuses_windows_temp_path_with_shell_characters(self):
        with TemporaryDirectory() as directory:
            risky = Path(directory) / "a&b"
            risky.mkdir()
            hwp = Path(directory) / "paper.hwp"
            hwp.write_bytes(b"x")

            class FixedTemp:
                def __init__(self, *a, **k): pass
                def __enter__(self): return str(risky)
                def __exit__(self, *a): return False

            with patch("app.exam_structure.find_kordoc", return_value="C:/npm/kordoc.cmd"), \
                 patch("app.exam_structure.sys.platform", "win32"), \
                 patch("app.exam_structure.tempfile.TemporaryDirectory", FixedTemp), \
                 patch("app.exam_structure.subprocess.Popen") as popen:
                with self.assertRaises(ExamReadError):
                    extract_exam_text(hwp)
            popen.assert_not_called()

    def test_find_kordoc_checks_usual_folders_when_path_is_minimal(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".local" / "bin").mkdir(parents=True)
            (home / ".local" / "bin" / "kordoc").write_text("")
            only_home = lambda path: str(path).startswith(str(home)) and path.exists()
            with patch("app.exam_structure.shutil.which", return_value=None), \
                 patch("app.exam_structure.Path.home", return_value=home), \
                 patch("app.exam_structure.sys.platform", "darwin"), \
                 patch("app.exam_structure.Path.is_file", only_home):
                self.assertEqual(Path(find_kordoc()).parts[-3:], (".local", "bin", "kordoc"))
            with patch("app.exam_structure.shutil.which", return_value=None), \
                 patch("app.exam_structure.Path.is_file", lambda path: False):
                self.assertEqual(find_kordoc(), "")

    @unittest.skipUnless(find_kordoc(), "kordoc not installed")
    def test_real_kordoc_reads_hwpx_offline(self):
        from app.exam_structure import _read_with_kordoc
        with TemporaryDirectory() as directory:
            hwpx = Path(directory) / "paper.hwpx"
            _hwpx(hwpx, PAPER)
            text = _read_with_kordoc(hwpx, find_kordoc())
        self.assertEqual(_summary(parse_exam_structure(text)), EXPECTED)


AUTO_NUMBERED = """<table><tr><td>2026학년도 정기시험 합성과목</td></tr></table>
※ 선택형 3문항, 논술형 2문항 / 총 5문항
첫째 합성 질문의 값은? [4.5점]

① 1	② 2	③ 3

④ 4	⑤ 5
둘째 합성 질문으로 옳은 것은? [4.6점]
① 가

② 나

③ 다

④ 라

⑤ 마
셋째 합성 질문은 줄이 길어 배점이 다음 줄로 넘어갔다.
[5.9점]
① 1	② 2	③ 3	④ 4	⑤ 5
합성 논술형 첫째 문항의 과정을 서술하시오.
합성 논술형 둘째 문항의 값을 구하고 이유를 쓰시오.
<유의사항>
논술형 문항 채점 기준표
논술형 1
① 첫 단계
1.0
5.0
② 둘째 단계
1.0
논술형 2
① 첫 단계
2.0
5.0
합계
10"""


class AutoNumberedPaperTests(unittest.TestCase):
    """HWP papers use 한글 auto numbering, so the extracted text has no item numbers."""

    def test_items_follow_choice_groups_and_rubric_gives_serdap_points(self):
        result = parse_exam_structure(AUTO_NUMBERED)
        self.assertEqual([(i["type"], i["number"], i["points"], i["choices"]) for i in result["items"]],
                         [("선택형", 1, 4.5, 5), ("선택형", 2, 4.6, 5), ("선택형", 3, 5.9, 5),
                          ("서답형", 1, 5.0, 0), ("서답형", 2, 5.0, 0)])
        self.assertIn("한글 자동 번호", result["warnings"][0])
        self.assertIn("채점 기준표에서 배점을 읽었습니다. 확인하세요.", result["items"][3]["flags"])
        self.assertTrue(result["items"][2]["preview"].startswith("[5.9점]") or "셋째" in result["items"][2]["preview"])

    def test_numbered_papers_keep_the_numbered_parser(self):
        self.assertNotIn("한글 자동 번호", " ".join(parse_exam_structure(PAPER)["warnings"]))

    def test_one_missing_point_is_filled_from_a_100_point_total(self):
        text = "\n".join(f"{n}. 문항 [20점]\n① 가" for n in range(1, 5)) + "\n5. 마지막 문항\n① 가"
        item = parse_exam_structure(text)["items"][-1]
        self.assertEqual(item["points"], 20.0)
        self.assertIn("총점 100점에서 나머지(20점)로 채웠습니다. 확인하세요.", item["flags"][-1])
        far = "\n".join(f"{n}. 문항 [19점]\n① 가" for n in range(1, 5)) + "\n5. 마지막 문항\n① 가"
        self.assertIsNone(parse_exam_structure(far)["items"][-1]["points"])  # 24점은 너무 커서 채우지 않는다


def _info(kind, number, difficulty, score, code="[10수학01-01]"):
    return SimpleNamespace(item_type=kind, number=number, difficulty=difficulty, score=score, standard_code=code, standard="합성 기준")


class EnrichStructureTests(unittest.TestCase):
    def _items(self):
        return [{"type": "선택형", "number": n, "points": p, "choices": 5, "flags": [], "preview": ""}
                for n, p in ((1, 4.0), (2, 5.0), (3, 6.0), (4, None))]

    def test_matching_item_info_gives_difficulty_standard_and_missing_points(self):
        info = [_info("선택형", 1, "쉬움", 4.0), _info("선택형", 2, "어려움", 5.0), _info("선택형", 3, "보통", 6.0),
                _info("선택형", 4, "보통", 7.0)]
        rows, source = enrich_structure(self._items(), info)
        self.assertEqual(source, "문항정보표")
        self.assertEqual([r["difficulty"] for r in rows], ["쉬움", "어려움", "보통", "보통"])
        self.assertEqual(rows[0]["standard"], "[10수학01-01] 합성 기준")
        self.assertEqual(rows[3]["points"], 7.0)
        self.assertIn("문항정보표 배점으로 채웠습니다.", rows[3]["flags"])

    def test_item_info_of_another_exam_is_not_used(self):
        other = [_info("선택형", n, "어려움", 9.0) for n in range(1, 5)]
        rows, source = enrich_structure(self._items(), other)
        self.assertEqual(source, "문항정보표 불일치")
        self.assertEqual([r["difficulty"] for r in rows], ["쉬움", "보통", "어려움", "보통"])  # 배점 순서 추정

    def test_without_item_info_difficulty_follows_points(self):
        rows, source = enrich_structure(self._items(), None)
        self.assertEqual(source, "배점 순서로 추정")
        self.assertEqual([r["difficulty"] for r in rows], ["쉬움", "보통", "어려움", "보통"])
        same = [dict(item, points=5.0) for item in self._items()]
        self.assertEqual({r["difficulty"] for r in enrich_structure(same, None)[0]}, {"보통"})


class ExamStructureToCalculatorTests(unittest.TestCase):
    def test_designs_need_points_and_use_each_rows_difficulty_and_target(self):
        calls = []
        rates_for = lambda target, difficulty: calls.append((target, difficulty)) or dict(zip("ABCDE", (90, 80, 70, 45, 25)))
        designs = designs_from_structure([
            {"type": "선택형", "number": 1, "points": 3.5, "difficulty": "쉬움", "target": "E", "standard": "[10수학01-01] 합성"},
            {"type": "서답형", "number": 1, "points": 6, "difficulty": "어려움", "target": "B"},
        ], rates_for)
        self.assertEqual([(d["type"], d["number"], d["points"], d["target"], d["difficulty"]) for d in designs],
                         [("선택형", 1, 3.5, "E", "쉬움"), ("서답형", 1, 6.0, "B", "어려움")])
        self.assertEqual(calls, [("E", "쉬움"), ("B", "어려움")])
        self.assertEqual(designs[0]["standard"], "[10수학01-01] 합성")
        for bad in (None, 0, -1):
            with self.assertRaises(ValueError):
                designs_from_structure([{"type": "선택형", "number": 2, "points": bad}], rates_for)

    @unittest.skipIf(MainWindow is None, "main window unavailable")
    def test_designs_become_a_valid_calculator_project(self):
        window = MainWindow.__new__(MainWindow)
        window.exam, window.overall = None, None
        rows, _ = enrich_structure(parse_exam_structure(PAPER)["items"], None)
        for row in rows:
            row["target"] = MainWindow._import_target_level(row)
        project = window._project_from_neis_targets(designs_from_structure(rows, window._target_level_rates))
        self.assertEqual([(i["type"], i["number"], i["points"]) for i in project["items"]],
                         [(t, n, p) for t, n, p, _ in EXPECTED])
        self.assertEqual([(i["difficulty"], i["targetLevel"]) for i in project["items"][:4]],
                         [("쉬움", "E"), ("보통", "C"), ("보통", "C"), ("어려움", "B")])  # 배점 3.5/4/4.5/5

    @unittest.skipIf(MainWindow is None, "main window unavailable")
    def test_import_target_uses_difficulty_rule_only(self):
        self.assertEqual([MainWindow._import_target_level({"difficulty": d}) for d in ("쉬움", "보통", "어려움")], ["E", "C", "B"])


@unittest.skipIf(MainWindow is None, "main window unavailable")
class ExamImportWindowTests(unittest.TestCase):
    def test_unreadable_file_warns_and_restores_cursor(self):
        window = MainWindow.__new__(MainWindow)
        with patch("app.main_window.QFileDialog.getOpenFileName", return_value=("/x/paper.hwpx", "")), \
             patch("app.main_window.extract_exam_text", side_effect=PermissionError("denied")), \
             patch("app.main_window.QApplication") as application, \
             patch("app.main_window.QMessageBox") as messages, \
             patch.object(MainWindow, "_show_exam_structure_dialog") as show:
            window.import_exam_structure()
        application.setOverrideCursor.assert_called_once()
        application.restoreOverrideCursor.assert_called_once()
        self.assertIn("권한", messages.warning.call_args.args[2])
        show.assert_not_called()


@unittest.skipIf(MainWindow is None, "main window unavailable")
class CalculatorProjectFetchTests(unittest.TestCase):
    """Qt returned JavaScript objects as '' here, which made every fetch look empty."""

    def test_fetch_sends_json_and_parses_it(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        window = MainWindow.__new__(MainWindow)
        window._spliter_loaded = True
        scripts, received = [], []
        page = SimpleNamespace(runJavaScript=lambda script, cb: (scripts.append(script), cb('{"items": [{"number": 1}]}')))
        window.spliter_view = Mock(page=Mock(return_value=page))
        window._fetch_spliter_project(received.append)
        self.assertTrue(scripts[0].startswith("JSON.stringify("))
        self.assertEqual(received, [{"items": [{"number": 1}]}])

    def test_parse_accepts_dicts_and_rejects_everything_else(self):
        parse = MainWindow._parse_spliter_project
        self.assertEqual(parse({"items": []}), {"items": []})
        self.assertEqual(parse('{"items": []}'), {"items": []})
        for raw in ("", None, "null", "[1, 2]", "{broken"):
            self.assertIsNone(parse(raw))


if __name__ == "__main__":
    unittest.main()
