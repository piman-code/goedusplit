import unittest
from types import MethodType, SimpleNamespace

from app.ai_review_logic import (
    ai_review_expected_values_from_rates,
    ai_review_target_from_counts,
)
try:
    from app.main_window import MainWindow
except ModuleNotFoundError as exc:
    MainWindow = None
    MAIN_WINDOW_IMPORT_ERROR = exc
else:
    MAIN_WINDOW_IMPORT_ERROR = None


def _stat(
    *,
    code="[10공수1-01-01]",
    standard="다항식의 사칙연산",
    content_area="다항식",
    difficulty="보통",
    p_by_level=None,
):
    return SimpleNamespace(
        item=SimpleNamespace(
            item_type="선택형",
            standard_code=code,
            standard=standard,
            content_area=content_area,
            difficulty=difficulty,
            score=5.0,
        ),
        p_by_level=p_by_level
        or {"A": 0.96, "B": 0.82, "C": 0.68, "D": 0.31, "E": 0.12},
    )


def _window_with_rows(rows):
    window = MainWindow.__new__(MainWindow)
    window.exam = None
    window.overall = None
    window.item_stats = []

    def rows_method(self):
        return rows

    window._ai_review_table_rows = MethodType(rows_method, window)
    return window


def _item(number, item_type="선택형", score=5.0):
    return SimpleNamespace(
        number=number,
        item_type=item_type,
        content_area="다항식",
        standard="다항식의 사칙연산",
        standard_code="[10공수1-01-01]",
        difficulty="보통",
        score=score,
    )


@unittest.skipIf(MainWindow is None, f"app.main_window unavailable: {MAIN_WINDOW_IMPORT_ERROR}")
class AIReviewLevelJudgmentTests(unittest.TestCase):
    def test_expected_values_from_previous_rates_choose_lowest_sufficient_level(self):
        expected, target, counts = ai_review_expected_values_from_rates(
            {"A": 0.96, "B": 0.82, "C": 0.68, "D": 0.31, "E": 0.12},
            sample_size=3,
        )

        self.assertEqual(target, "C")
        self.assertEqual(ai_review_target_from_counts(counts, 3), "C")
        self.assertEqual(expected["A 예상"], "3/3")
        self.assertEqual(expected["B 예상"], "2/3")
        self.assertEqual(expected["C 예상"], "2/3")
        self.assertEqual(expected["D 예상"], "1/3")
        self.assertEqual(expected["E 예상"], "0/3")

    def test_local_draft_uses_loaded_exam_item_level_rates(self):
        window = MainWindow.__new__(MainWindow)
        window.item_stats = [_stat()]
        block = {
            "kind": "문항",
            "label": "1번",
            "section_type": "선택형",
            "text": "1번 [10공수1-01-01] 다항식의 사칙연산을 활용하여 값을 구하시오. 배점 5점",
        }

        row = MainWindow._infer_ai_review_row(window, block, [])

        self.assertEqual(row["target"], "C")
        self.assertEqual(row["A 예상"], "3/3")
        self.assertEqual(row["C 예상"], "2/3")
        self.assertIn("이전시험", row["evidence"])
        self.assertIn("성취수준별 정답률", row["evidence"])

    def test_local_draft_does_not_use_previous_rates_without_real_match(self):
        window = MainWindow.__new__(MainWindow)
        window.item_stats = [_stat()]
        block = {
            "kind": "문항",
            "label": "2번",
            "section_type": "선택형",
            "text": "2번 선택형 새로운 실생활 모델링 문항입니다. 보기 ① ② ③ ④ ⑤ 배점 8점",
        }

        row = MainWindow._infer_ai_review_row(window, block, [])

        self.assertNotIn("이전시험", row["evidence"])
        self.assertEqual(row["target"], "B")
        self.assertIn("성취기준 코드 확인", row["next_step"])

    def test_explicit_ai_review_points_win_over_previous_exam_same_number(self):
        window = MainWindow.__new__(MainWindow)
        window.exam = SimpleNamespace(
            items=[
                SimpleNamespace(number=2, item_type="선택형", score=4.5),
            ]
        )
        row = {
            "번호/요소": "2번",
            "성취기준 후보": "[10공수1-99-99] 새 문항",
            "근거": "배점 8점 · 실생활 · 모델링",
            "다음 확인": "성취기준 코드 확인",
        }

        points = MainWindow._ai_review_points_for_row(window, 2, "선택형", row, 5.0)

        self.assertEqual(points, 8.0)

    def test_split_embedded_item_labels_from_pdf_text(self):
        text = "1. 첫 문항입니다. ① 1 ② 2 2. 둘째 문항입니다. ① 3 ② 4 문항 3 | 유형 선택형 | 배점 5"

        blocks = MainWindow._split_ai_review_blocks(MainWindow.__new__(MainWindow), text)

        self.assertEqual([block["label"] for block in blocks], ["1번", "2번", "3번"])

    def test_supplements_missing_rows_from_loaded_item_info(self):
        window = MainWindow.__new__(MainWindow)
        window.exam = SimpleNamespace(
            items=[_item(n, "선택형") for n in range(1, 19)]
            + [_item(1, "서답형", 6.0), _item(2, "서답형", 7.0)]
        )
        window.item_stats = [
            _stat(code="[10공수1-01-01]", p_by_level={"A": 0.9, "B": 0.8, "C": 0.7, "D": 0.4, "E": 0.2})
        ]
        rows = [
            {
                "kind": "문항",
                "label": f"{n}번",
                "review_type": "선택형",
                "target": "C",
                "difficulty": "보통",
                "standard": "[10공수1-01-01] 다항식",
                "A 예상": "3/3",
                "B 예상": "3/3",
                "C 예상": "2/3",
                "D 예상": "1/3",
                "E 예상": "0/3",
                "evidence": "원문",
                "next_step": "",
            }
            for n in range(1, 16)
        ]

        supplemented, added = MainWindow._supplement_ai_review_rows_from_exam(window, rows)

        self.assertEqual(len(supplemented), 20)
        self.assertEqual(added, 5)
        added_rows = supplemented[-5:]
        self.assertTrue(all("문항정보표 보충" in row["evidence"] for row in added_rows))
        self.assertTrue(all("문항 원문 확인" in row["next_step"] for row in added_rows))
        self.assertEqual([row["label"] for row in added_rows[:3]], ["16번", "17번", "18번"])
        self.assertEqual([row["review_type"] for row in added_rows[-2:]], ["서답형", "서답형"])

    def test_supplemented_rows_are_sorted_by_item_number(self):
        window = MainWindow.__new__(MainWindow)
        window.exam = SimpleNamespace(items=[_item(n, "선택형") for n in range(1, 6)])
        window.item_stats = []
        rows = [
            {
                "kind": "문항",
                "label": f"{n}번",
                "review_type": "선택형",
                "target": "C",
                "difficulty": "보통",
                "standard": "[10공수1-01-01] 다항식",
                "A 예상": "3/3",
                "B 예상": "3/3",
                "C 예상": "2/3",
                "D 예상": "1/3",
                "E 예상": "0/3",
                "evidence": "원문",
                "next_step": "",
            }
            for n in (4, 5)
        ]

        supplemented, added = MainWindow._supplement_ai_review_rows_from_exam(window, rows)

        self.assertEqual(added, 3)
        self.assertEqual([row["label"] for row in supplemented], ["1번", "2번", "3번", "4번", "5번"])

    def test_merge_reorders_ai_rows_by_item_number(self):
        window = MainWindow.__new__(MainWindow)
        local_rows = [
            {
                "kind": "문항",
                "label": "1번",
                "review_type": "선택형",
                "target": "C",
                "difficulty": "보통",
                "standard": "[10공수1-01-01] 다항식",
                "A 예상": "3/3",
                "B 예상": "3/3",
                "C 예상": "2/3",
                "D 예상": "1/3",
                "E 예상": "0/3",
                "evidence": "배점 5점 · 원문",
                "next_step": "",
            },
            {
                "kind": "문항",
                "label": "2번",
                "review_type": "선택형",
                "target": "B",
                "difficulty": "어려움",
                "standard": "[10공수1-01-02] 나머지정리",
                "A 예상": "3/3",
                "B 예상": "2/3",
                "C 예상": "1/3",
                "D 예상": "0/3",
                "E 예상": "0/3",
                "evidence": "배점 8점 · 원문",
                "next_step": "",
            },
        ]
        ai_rows = [
            {
                "구분": "문항",
                "번호/요소": "2번",
                "성취기준 후보": "[10공수1-01-02] 나머지정리",
                "평가유형": "선택형",
                "목표수준 후보": "B",
                "난이도 후보": "어려움",
                "A 예상": "3/3",
                "B 예상": "2/3",
                "C 예상": "1/3",
                "D 예상": "0/3",
                "E 예상": "0/3",
                "근거": "배점 8점 · 나머지정리",
                "다음 확인": "",
            },
            {
                "구분": "문항",
                "번호/요소": "1번",
                "성취기준 후보": "[10공수1-01-01] 다항식",
                "평가유형": "선택형",
                "목표수준 후보": "C",
                "난이도 후보": "보통",
                "A 예상": "3/3",
                "B 예상": "3/3",
                "C 예상": "2/3",
                "D 예상": "1/3",
                "E 예상": "0/3",
                "근거": "배점 5점 · 다항식",
                "다음 확인": "",
            },
        ]

        merged = MainWindow._ai_review_merge_chunk_rows(window, local_rows, ai_rows)

        self.assertEqual([row["번호/요소"] for row in merged], ["1번", "2번"])
        self.assertEqual([row["성취기준 후보"] for row in merged], ["[10공수1-01-01] 다항식", "[10공수1-01-02] 나머지정리"])

    def test_reference_entries_accept_general_standard_codes(self):
        window = MainWindow.__new__(MainWindow)
        reference = (
            "[12수학I-01-01] 지수법칙을 이해하고 식을 변형할 수 있다. "
            "A 수준 복합식을 일반화한다. B 수준 식의 구조를 설명한다."
        )

        entries = MainWindow._ai_reference_entries(window, reference)
        compacted = MainWindow._compact_ai_reference_text(window, reference)

        self.assertEqual(entries[0]["code"], "[12수학I-01-01]")
        self.assertIn("[12수학I-01-01]", compacted)
        self.assertIn("A:", compacted)

    def test_reference_chunk_uses_source_text_to_select_relevant_standard(self):
        window = MainWindow.__new__(MainWindow)
        reference = (
            "[10공수1-01-01] 다항식의 사칙연산을 이해하고 계산할 수 있다.\n"
            "[10공수1-01-02] 항등식의 성질과 나머지정리를 이해하고 활용할 수 있다. "
            "A 수준 나머지정리를 식의 구조와 연결한다. C 수준 기본 나머지를 구한다.\n"
            "[10공수1-03-01] 경우의 수 기본 원리를 이해한다."
        )
        entries = MainWindow._ai_reference_entries(window, reference)
        rows = [{"label": "4번", "standard": "(후보 없음)", "evidence": ""}]

        selected = MainWindow._ai_reference_text_for_review_chunk(
            window,
            rows,
            entries,
            reference,
            "4번 다항식 P(x)를 x+1로 나누었을 때의 나머지를 나머지정리로 구하시오.",
        )

        self.assertIn("[10공수1-01-02]", selected)

    def test_structured_prompt_requires_item_standard_and_level_evidence(self):
        window = MainWindow.__new__(MainWindow)
        prompt = MainWindow._make_structured_ai_review_prompt(
            window,
            [{"label": "1번", "review_type": "선택형", "target": "C", "difficulty": "보통"}],
            "1번 나머지정리를 활용하는 문항",
            "[10공수1-01-02] 나머지정리 A: 식의 구조를 설명한다. C: 기본 나머지를 구한다.",
            row_limit=1,
        )

        self.assertIn("문항: ... / 기준: ... / 수준: ...", prompt)
        self.assertIn("문항 단서와 참고자료 단서", prompt)
        self.assertIn("근거 부족", prompt)

    def test_unsupported_standard_change_keeps_local_standard(self):
        window = MainWindow.__new__(MainWindow)
        local_row = {
            "kind": "문항",
            "label": "6번",
            "review_type": "선택형",
            "target": "C",
            "difficulty": "보통",
            "standard": "[10공수1-01-01] 다항식의 사칙연산",
            "A 예상": "3/3",
            "B 예상": "3/3",
            "C 예상": "2/3",
            "D 예상": "1/3",
            "E 예상": "0/3",
            "evidence": "문항정보표 성취기준",
            "next_step": "",
        }
        ai_row = {
            "구분": "문항",
            "번호/요소": "6번",
            "성취기준 후보": "[10공수1-03-01] 경우의 수 기본 원리",
            "평가유형": "선택형",
            "목표수준 후보": "C",
            "난이도 후보": "보통",
            "A 예상": "3/3",
            "B 예상": "3/3",
            "C 예상": "2/3",
            "D 예상": "1/3",
            "E 예상": "0/3",
            "근거": "문항: 계산 / 기준: 경우의 수",
            "다음 확인": "",
        }

        normalized = MainWindow._normalize_ai_review_output_row(window, ai_row, local_row)

        self.assertEqual(normalized["성취기준 후보"], "[10공수1-01-01] 다항식의 사칙연산")
        self.assertIn("AI 성취기준 근거 확인", normalized["다음 확인"])

    def test_target_change_needs_more_than_points_only(self):
        window = MainWindow.__new__(MainWindow)
        local_row = {
            "kind": "문항",
            "label": "7번",
            "review_type": "선택형",
            "target": "C",
            "difficulty": "보통",
            "standard": "[10공수1-01-02] 나머지정리",
            "A 예상": "3/3",
            "B 예상": "3/3",
            "C 예상": "2/3",
            "D 예상": "1/3",
            "E 예상": "0/3",
            "evidence": "문항정보표 성취기준",
            "next_step": "",
        }
        ai_row = {
            "구분": "문항",
            "번호/요소": "7번",
            "성취기준 후보": "[10공수1-01-02] 나머지정리",
            "평가유형": "선택형",
            "목표수준 후보": "B",
            "난이도 후보": "어려움",
            "A 예상": "3/3",
            "B 예상": "2/3",
            "C 예상": "1/3",
            "D 예상": "0/3",
            "E 예상": "0/3",
            "근거": "배점 8점",
            "다음 확인": "",
        }

        normalized = MainWindow._normalize_ai_review_output_row(window, ai_row, local_row)

        self.assertEqual(normalized["목표수준 후보"], "C")
        self.assertEqual(normalized["난이도 후보"], "보통")
        self.assertIn("AI 목표수준 근거 확인", normalized["다음 확인"])

    def test_weak_ai_evidence_keeps_local_target_and_standard(self):
        window = MainWindow.__new__(MainWindow)
        local_row = {
            "kind": "문항",
            "label": "9번",
            "review_type": "선택형",
            "target": "B",
            "difficulty": "어려움",
            "standard": "[10공수1-01-02] 항등식과 나머지정리",
            "A 예상": "3/3",
            "B 예상": "2/3",
            "C 예상": "1/3",
            "D 예상": "0/3",
            "E 예상": "0/3",
            "evidence": "이전시험 유사 문항 성취수준별 정답률(A90/B70/C40)",
            "next_step": "",
        }
        ai_row = {
            "구분": "지필",
            "번호/요소": "9번",
            "성취기준 후보": "경우의 수 기본 원리",
            "평가유형": "선택형",
            "목표수준 후보": "D",
            "난이도 후보": "쉬움",
            "A 예상": "3/3",
            "B 예상": "3/3",
            "C 예상": "3/3",
            "D 예상": "2/3",
            "E 예상": "1/3",
            "근거": "경우의 수 기본 원리",
            "다음 확인": "",
        }

        normalized = MainWindow._normalize_ai_review_output_row(window, ai_row, local_row)

        self.assertEqual(normalized["성취기준 후보"], "[10공수1-01-02] 항등식과 나머지정리")
        self.assertEqual(normalized["목표수준 후보"], "B")
        self.assertEqual(normalized["난이도 후보"], "어려움")
        self.assertIn("이전시험", normalized["근거"])
        self.assertIn("AI 목표수준 근거 확인", normalized["다음 확인"])

    def test_build_project_defaults_blank_type_and_enforces_target_pattern(self):
        window = _window_with_rows([
            {
                "번호/요소": "2번",
                "성취기준 후보": "[10공수1-01-01] 다항식",
                "평가유형": "",
                "목표수준 후보": "B",
                "난이도 후보": "상",
                "A 예상": "0/3",
                "B 예상": "0/3",
                "C 예상": "3/3",
                "D 예상": "3/3",
                "E 예상": "3/3",
                "근거": "AI 출력 일부 확인 필요",
                "다음 확인": "교사 확인",
            }
        ])

        project = MainWindow._build_ai_review_spliter_project(window)

        self.assertIsNotNone(project)
        item = project["items"][0]
        self.assertEqual(item["type"], "선택형")
        self.assertEqual(item["targetLevel"], "B")
        counts = [
            sum(item["judgmentsByJudge"]["teacher-1"][lv]["correct"])
            for lv in ["A", "B", "C", "D", "E"]
        ]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertGreaterEqual(counts[0], 2)
        self.assertGreaterEqual(counts[1], 2)
        self.assertLessEqual(counts[2], 2)
        self.assertIn("교사 확인 필요", item["note"])


if __name__ == "__main__":
    unittest.main()
