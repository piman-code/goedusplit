"""Synthetic candidate QA must be explicit and preserve its input contract."""
from tests.runtime_isolation import ensure_isolated
ensure_isolated()

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.synthetic_qa import business_values, project_fixture, main


class CandidateQaContract(unittest.TestCase):
    def test_fixture_preserves_zero_hundred_fractional_rates_and_points(self):
        fixture=project_fixture()
        self.assertEqual([item['points'] for item in fixture['items']],[1.5,3.25])
        rates=fixture['items'][0]['judgmentsByJudge']['j1']
        self.assertEqual((rates['A']['overrideRate'],rates['C']['overrideRate'],rates['E']['overrideRate']),(100,63.25,0))
        changed=copy.deepcopy(fixture)
        changed['items'][0]['judgmentsByJudge']['j1']['C']['overrideRate']=63
        self.assertNotEqual(business_values(fixture),business_values(changed))

    def test_existing_output_is_rejected_before_window_or_settings_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel=Path(directory)/'keep.txt';sentinel.write_bytes(b'untouched')
            with patch('sys.argv',['Goedu-Split','--synthetic-qa',directory]), patch('app.synthetic_qa.run') as run:
                with self.assertRaises(FileExistsError):main()
                run.assert_not_called()
            self.assertEqual(sentinel.read_bytes(),b'untouched')

    def test_missing_qa_argument_creates_no_runtime(self):
        with patch('sys.argv',['Goedu-Split']), patch('app.synthetic_qa.run') as run:
            with self.assertRaises(SystemExit):main()
            run.assert_not_called()
