"""Pure synthetic saved-work detail contracts; never opens operating data."""
import copy
from dataclasses import asdict
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from app.data_loader import ExamData, ItemInfo, StudentResponse
from app.perform_loader import PerformData, PerformArea, PerformRecord
from app.work_sessions import build_session, WorkSessionStore
from app.portfolio_details import load_work_session_rows, resolve_details, current_revision, presentation_rows


class PortfolioDetailsTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='goedusplit-detail-test-'))
        self.exam=ExamData(subject='합성수학',grade='1',semester='2026학년도 1학기 1차',
            items=[ItemInfo(1,'선택형',score=50,answer='1',standard='기준1'),
                   ItemInfo(2,'선택형',score=50,answer='3',standard='기준2')],
            students=[StudentResponse('syn1','1/1','1','합성하나',{1:'.',2:'2'},total=50,final_score=63.25,perform_score=80),
                      StudentResponse('syn2','1/2','1','합성둘',{1:'',2:'.'},total=50,final_score=50)])
        record=PerformRecord('syn1','1/1','합성하나',{'탐구':32},32,80)
        self.perform=PerformData('합성수학',[PerformArea('탐구',40,40)],40,40,{'syn1':record},{'1/1':record})
        self.window=SimpleNamespace(exam=self.exam,perform_data=self.perform,
            _ai_material_root_dir=lambda:self.root,_portfolio_hash_key=lambda:b'synthetic-key-only-00000000000000',
            _detect_exam_round=lambda:(2026,1,1))
        self.store=WorkSessionStore(self.root/'work_sessions')
        self.payload=build_session(self.exam,self.perform,{'widgets':{'cmb_round':{'text':'1학기 1차'}},'inputs':{}},None)
        self.path=self.store.save(self.payload)

    def point(self):
        return next(r for r in load_work_session_rows(self.window) if r['name']=='합성하나')

    def test_saved_work_alone_produces_timeline_rows(self):
        rows=load_work_session_rows(self.window)
        self.assertEqual(2,len(rows))
        self.assertEqual({(2026,1,1)},{(r['year'],r['semester_no'],r['round_no']) for r in rows})
        self.assertTrue(all(r['source_kind']=='work-session' for r in rows))
        self.assertEqual(56.625,rows[0]['class_mean'])

    def test_real_detail_values_responses_and_percentages(self):
        result=resolve_details(self.window,self.point())
        tabs=result['tabs']
        self.assertTrue(all(tabs[k]['available'] for k in tabs))
        self.assertEqual(['반/번호','이름','성취도','9등급','5등급','원점수','정기시험 총점','문1','문2'],tabs['data']['headers'])
        self.assertEqual(63,tabs['data']['rows'][0][5])
        self.assertEqual(['.','2'],tabs['data']['rows'][0][-2:])
        self.assertEqual([['탐구',40,40,32]],tabs['perform']['rows'])
        self.assertEqual(50,tabs['choice']['rows'][0][4])  # one unanswered / two students
        self.assertEqual(50,tabs['choice']['rows'][0][5])  # one selected answer 1
        self.assertEqual(50,tabs['standards']['rows'][0][2])
        self.assertEqual('합성하나',tabs['data']['rows'][0][1])
        self.assertFalse(any(sid in str(tabs) for sid in ('syn1','syn2')))
        self.assertIn('A 정답률(%)',tabs['standards']['headers'])
        self.assertIn('E',[r[3] for r in tabs['choice']['rows']])

    def test_saved_revision_does_not_use_different_live_analysis(self):
        point=self.point()
        before=self.path.read_bytes()
        self.window.exam=copy.deepcopy(self.exam)
        self.window.exam.students[0].answers[1]='4'
        self.window.exam.subject='다른 과목'
        result=resolve_details(self.window,point)
        self.assertEqual('.',result['tabs']['data']['rows'][0][-2])
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual('4',self.window.exam.students[0].answers[1])

    def test_wrong_student_subject_round_or_revision_refuses_details(self):
        original=self.point()
        for field,value in [('student_hash','missing'),('subject','다른 과목'),('round_no',2),('detail_revision','wrong')]:
            with self.subTest(field=field):
                point=dict(original);point[field]=value
                result=resolve_details(self.window,point)
                self.assertFalse(result['tabs']['items']['available'])
                self.assertIn('중단',result['provenance'])

    def test_summary_never_borrows_current_or_saved_responses(self):
        point=self.point();point['source_kind']='summary'
        result=resolve_details(self.window,point)
        self.assertFalse(result['tabs']['choice']['available'])
        self.assertNotIn('1번 응답',result['tabs']['data']['headers'])
        self.assertIn('요약',result['provenance'])

    def test_current_preview_requires_unchanged_live_revision(self):
        point=self.point();point.update(source_kind='current',is_current_preview=True,detail_revision=current_revision(self.window))
        self.assertTrue(resolve_details(self.window,point)['tabs']['items']['available'])
        self.exam.students[0].answers[1]='4'
        self.assertFalse(resolve_details(self.window,point)['tabs']['items']['available'])

    def test_other_paths_rejected_and_malformed_records_preserved(self):
        point=self.point();point['work_session_path']=str(self.root/'outside.json')
        self.assertFalse(resolve_details(self.window,point)['tabs']['items']['available'])
        bad=self.root/'work_sessions'/'work_broken.json';bad.write_text('{}')
        self.assertEqual(2,len(load_work_session_rows(self.window)))
        self.assertEqual('{}',bad.read_text())

    def test_load_and_details_do_not_mutate_live_domain(self):
        before=(asdict(self.exam),asdict(self.perform))
        resolve_details(self.window,self.point())
        self.assertEqual(before,(asdict(self.exam),asdict(self.perform)))

    def test_data_identity_is_masked_in_counseling_mode(self):
        self.window._counseling_mode_enabled=lambda:True
        for kind in ('work-session','summary'):
            point=self.point();point['source_kind']=kind
            result=resolve_details(self.window,point)
            self.assertNotIn('합성하나',str(result['tabs']))
            self.assertNotIn('1/1',str(result['tabs']))
            self.assertEqual('상담 학생',result['tabs']['data']['rows'][0][1])

    def test_performance_column_and_verified_class_fallback(self):
        self.exam.use_perform=True
        self.perform.records={}
        self.path=self.store.save(build_session(self.exam,self.perform,self.payload['ui_state'],None))
        points=[r for r in load_work_session_rows(self.window) if r['work_session_path']==str(self.path)]
        point=next(r for r in points if r['name']=='합성하나')
        result=resolve_details(self.window,point)
        self.assertIn('수행환산',result['tabs']['data']['headers'])
        self.assertEqual([['탐구',40,40,32]],result['tabs']['perform']['rows'])

    def test_saved_file_revision_change_is_rejected_even_when_domain_unchanged(self):
        point=self.point()
        import json
        altered=copy.deepcopy(self.payload);altered['metadata']['name']='different revision'
        self.path.write_text(json.dumps(altered),encoding='utf-8')
        self.assertFalse(resolve_details(self.window,point)['tabs']['items']['available'])

    def test_saved_summary_and_live_details_remain_distinct_presentation_records(self):
        from app.portfolio_timeline import build_timeline
        point=self.point()
        summary=dict(point,source_kind='summary',detail_revision='',work_session_path='')
        self.window._portfolio_has_preview=False
        self.window._current_identity_by_hash=lambda:{point['student_hash']:('1/1','합성하나')}
        self.window._current_subject_snapshot=lambda:dict(subject=self.exam.subject,grade='1',
            semester=self.exam.semester,year=2026,semester_no=1,round_no=1,
            students=[dict(student_hash=point['student_hash'],final_score=63.25,rounded_score=63,
                           pencil_total=50,perform_score=80,level='D')])
        original=[summary]
        visible=presentation_rows(self.window,original)
        self.assertEqual(1,len(original))
        self.assertEqual(2,len(visible))
        live=next(r for r in visible if r['source_kind']=='current')
        self.assertTrue(live['is_current_analysis'])
        self.assertFalse(live['is_current_preview'])
        self.assertTrue(resolve_details(self.window,live)['tabs']['items']['available'])
        self.assertFalse(resolve_details(self.window,summary)['tabs']['items']['available'])
        model=build_timeline(visible,point['student_hash'],point['subject'])
        self.assertEqual('current',model['points'][0]['source_kind'])
