import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.exam_structure import (
    ExamReadError, designs_from_structure, extract_exam_text, find_kordoc, markdown_to_lines, parse_exam_structure,
)

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

    def test_kordoc_runs_offline_without_shell(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="1\\. 문제 [5점]\n\n① 가", stderr="")

        with TemporaryDirectory() as directory:
            hwp = Path(directory) / "시험 지; rm -rf.hwp"
            hwp.write_bytes(b"x")
            with patch("app.exam_structure.find_kordoc", return_value="/fake/kordoc"), \
                 patch("app.exam_structure.subprocess.run", side_effect=fake_run):
                text, how = extract_exam_text(hwp)
        command, kwargs = calls[0]
        self.assertEqual(command, ["/fake/kordoc", str(hwp), "--silent"])  # 파일명은 인자 하나로만 전달
        self.assertEqual(kwargs["env"]["KORDOC_OFFLINE"], "1")
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(how, "kordoc(오프라인)")
        self.assertEqual(_summary(parse_exam_structure(text)), [("선택형", 1, 5.0, 1)])

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


class ExamStructureToCalculatorTests(unittest.TestCase):
    def test_designs_need_points_and_carry_default_rates(self):
        rates = dict(zip("ABCDE", (90, 80, 70, 45, 25)))
        designs = designs_from_structure([{"type": "선택형", "number": 1, "points": 3.5},
                                          {"type": "서답형", "number": 1, "points": 6}], rates)
        self.assertEqual([(d["type"], d["number"], d["points"], d["target"], d["difficulty"]) for d in designs],
                         [("선택형", 1, 3.5, "C", "보통"), ("서답형", 1, 6.0, "C", "보통")])
        self.assertEqual(designs[0]["rates"], rates)
        for bad in (None, 0, -1):
            with self.assertRaises(ValueError):
                designs_from_structure([{"type": "선택형", "number": 2, "points": bad}], rates)

    @unittest.skipIf(MainWindow is None, "main window unavailable")
    def test_designs_become_a_valid_calculator_project(self):
        window = MainWindow.__new__(MainWindow)
        window.exam, window.overall = None, None
        rates = window._target_level_rates("C", "보통")
        result = parse_exam_structure(PAPER)
        project = window._project_from_neis_targets(designs_from_structure(result["items"], rates))
        self.assertEqual([(i["type"], i["number"], i["points"]) for i in project["items"]],
                         [(t, n, p) for t, n, p, _ in EXPECTED])
        self.assertEqual({i["targetLevel"] for i in project["items"]}, {"C"})


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
