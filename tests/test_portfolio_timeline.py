"""Pure synthetic history tests; no files, settings, or GUI required."""
import copy
import unittest
from app.portfolio_timeline import build_timeline


def row(round_no=1, **extra):
    result = dict(student_hash='synthetic-hash', subject='합성수학', year=2026,
                  semester_no=1, round_no=round_no, grade='1', score=63.25,
                  class_mean=None, saved_at='2026-10-18T12:00:00',
                  snapshot_path=f'/synthetic/{round_no}.json', is_current_preview=False)
    result.update(extra)
    return result


class PortfolioTimelineTests(unittest.TestCase):
    def model(self, rows, subject=None):
        return build_timeline(rows, 'hash:synthetic-hash', subject)

    def test_exam_order_uses_year_semester_round_not_saved_timestamp(self):
        rows = [row(1, year=2027, saved_at='2020-01-01'), row(2),
                row(1, saved_at='2030-01-01'), row(1, semester_no=2)]
        points = self.model(rows)['points']
        self.assertEqual([(2026,1,1),(2026,1,2),(2026,2,1),(2027,1,1)],
                         [(p['year'],p['semester_no'],p['round_no']) for p in points])

    def test_latest_same_round_selected_but_every_revision_remains(self):
        rows = [row(score=20),row(score=80,saved_at='2026-10-18T13:00:00')]
        model = self.model(rows)
        self.assertEqual(80, model['points'][0]['score'])
        self.assertEqual(2, model['points'][0]['revision_count'])
        self.assertEqual(2, len(model['history']))

    def test_current_preview_wins_even_when_save_has_future_date(self):
        model = self.model([row(score=100,saved_at='2099-01-01'),
                           row(score=0,is_current_preview=True,saved_at='현재 분석 (미저장)')])
        self.assertEqual(0, model['points'][0]['score'])
        self.assertTrue(model['points'][0]['is_current_preview'])

    def test_subjects_never_share_a_line(self):
        rows = [row(subject='합성영어',score=20), row(subject='합성수학',score=80)]
        model = self.model(rows,'합성수학')
        self.assertEqual(['합성수학'], [p['subject'] for p in model['points']])
        self.assertEqual(2,len(model['subjects']))
        self.assertEqual(2,len(model['history']))
        self.assertEqual([],self.model(rows,'존재하지 않는 과목')['points'])

    def test_default_subject_prefers_current_analysis(self):
        model = self.model([row(subject='A'),row(subject='Z',is_current_preview=True)])
        self.assertEqual('Z', model['selected_subject'])
        self.assertEqual(1,len(model['points']))

    def test_unknown_class_mean_is_not_zero_or_inferred_from_other_students(self):
        model = self.model([row(class_no='1/1'),row(student_hash='other',score=100,class_no='1/2')])
        self.assertIsNone(model['points'][0]['class_mean'])
        self.assertEqual(1,len(model['history']))
        self.assertEqual(0,self.model([row(class_mean=0)])['points'][0]['class_mean'])

    def test_nonfinite_and_missing_scores_remain_unknown(self):
        for value in (None,'',float('nan'),float('inf'),True):
            with self.subTest(value=value):
                point=self.model([row(score=value,class_mean=value)])['points'][0]
                self.assertIsNone(point['score'])
                self.assertIsNone(point['class_mean'])

    def test_legacy_term_with_explicit_date_parses_without_mutation(self):
        rows=[row(year=None,semester_no=None,round_no=None,
                  term='2025학년도 2학기 1학년 · 2차')]
        before=copy.deepcopy(rows)
        model=self.model(rows)
        self.assertEqual((2025,2,2),tuple(model['points'][0][k] for k in ('year','semester_no','round_no')))
        model['points'][0]['score']=99
        model['history'][0]['score']=11
        self.assertEqual(before,rows)

    def test_unknown_exam_does_not_collapse_unrelated_legacy_records(self):
        rows=[row(year=None,score=20),row(year=None,score=40)]
        self.assertEqual(0,len(self.model(rows)['points']))
        self.assertEqual(2,len(self.model(rows)['unknown_points']))

    def test_unselected_or_unknown_identity_never_combines_students(self):
        self.assertEqual([],build_timeline([row()],None)['points'])
        self.assertEqual([],build_timeline([row()],'hash:missing')['points'])
        self.assertEqual(1,len(build_timeline([row()],'synthetic-hash')['points']))

    def test_same_second_legacy_revision_uses_file_time_before_random_name(self):
        rows = [row(score=20,snapshot_path='/synthetic/z-uuid.json',snapshot_mtime_ns=1000000001),
                row(score=80,snapshot_path='/synthetic/a-uuid.json',snapshot_mtime_ns=1000000002)]
        self.assertEqual(80,self.model(rows)['points'][0]['score'])
        self.assertEqual(2,len(self.model(rows)['history']))

    def test_subsecond_saved_timestamp_precedes_mtime_for_copied_new_records(self):
        rows = [row(score=20,saved_at='2026-10-18T12:00:00.100001',snapshot_mtime_ns=999),
                row(score=80,saved_at='2026-10-18T12:00:00.100002',snapshot_mtime_ns=1)]
        self.assertEqual(80,self.model(rows)['points'][0]['score'])
