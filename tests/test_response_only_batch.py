from tests.runtime_isolation import ensure_isolated
ensure_isolated()
import tempfile
import unittest
from pathlib import Path
from app.synthetic_qa import analysis_fixtures
from app.folder_batch import discover_round_groups,prepare_round_groups
from app.data_loader import load_exam,load_student_responses_many
DEFAULT_CUTS={"A":90,"B":80,"C":70,"D":60,"E":40}
from app.analysis import analyze_items,analyze_overall

class ResponseOnlyBatchTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='response-only-'))
        source=self.root/'source';source.mkdir()
        self.item,responses,_=analysis_fixtures(source)
        self.folder=self.root/'first-only';self.folder.mkdir()
        self.responses=[]
        for i,path in enumerate(responses[1],1):
            target=self.folder/f'2026학년도 1학기 1차 정오표(1-{i}).xlsx'
            target.write_bytes(path.read_bytes());self.responses.append(str(target))
    def test_first_round_response_only_preserves_real_scores_without_fake_items(self):
        original={p:p.read_bytes() for p in self.folder.iterdir()}
        students,_,_=load_student_responses_many(self.responses)
        groups=discover_round_groups(self.folder,'2학기 2차')
        self.assertEqual(1,len(groups));self.assertEqual((1,1),groups[0]['key'][1:3])
        self.assertFalse(groups[0]['problems']);self.assertTrue(groups[0]['warnings'])
        prepared=prepare_round_groups(groups,DEFAULT_CUTS,60,40)
        exam=prepared[0][1]
        self.assertEqual([],exam.items)
        self.assertEqual((100,0),(exam.weight_pencil,exam.weight_perform))
        self.assertTrue(any("학기총점 아님" in text for text in groups[0]["warnings"]))
        self.assertEqual([s.total for s in students],[s.final_score for s in exam.students])
        self.assertEqual([s.answers for s in students],[s.answers for s in exam.students])
        stats,matrix,_=analyze_items(exam);self.assertEqual([],stats)
        self.assertIsNotNone(analyze_overall(exam,matrix))
        self.assertEqual(original,{p:p.read_bytes() for p in original})
    def test_explicit_broken_item_file_is_not_treated_as_absent(self):
        broken=self.root/'broken.xlsx';broken.write_text('not an Excel workbook')
        with self.assertRaises(Exception):load_exam(str(broken),self.responses)
    def test_no_item_path_is_empty_in_saved_sources(self):
        exam=load_exam(None,self.responses)
        self.assertEqual('',exam.source_files['item_info'])
        self.assertTrue(exam.students);self.assertFalse(exam.items)
