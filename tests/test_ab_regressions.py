import unittest
from ab_proofread.core import parse_matches, corrected_text

class RegressionTests(unittest.TestCase):
    def test_insertion_and_technical_domains(self):
        text = 'Hello world test.example 0123456789abcdef0123456789abcdef'
        matches = [
            {'offset': 5, 'length': 0, 'message': 'comma', 'replacements': [{'value': ','}], 'rule': {'id': 'COMMA'}},
            {'offset': 12, 'length': 4, 'replacements': [{'value': 'best'}]},
            {'offset': 25, 'length': 32, 'replacements': [{'value': 'no'}]},
        ]
        proposals = parse_matches(text, {'matches': matches})
        self.assertEqual(len(proposals), 1)
        self.assertEqual(corrected_text(text, proposals, {0: ','}), 'Hello, world test.example 0123456789abcdef0123456789abcdef')
