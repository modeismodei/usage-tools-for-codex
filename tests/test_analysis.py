import unittest
from codex_limit_tools.estimate import analysis_interval, estimate
from analysis_fixtures import LARGE, UNEVEN, RESET, PAUSE, MIDNIGHT, PARTIAL, segment


class Contracts(unittest.TestCase):
    def test_large_observed_interval(self):
        row = analysis_interval(segment(), *LARGE)
        self.assertTrue(row['included'])
        self.assertEqual((row['start']['remaining'], row['end']['remaining']), (73, 40))
        self.assertEqual(row['points'], 33)
        self.assertEqual(row['delta']['cost'], 132)
        result = estimate(*LARGE)
        self.assertEqual(result['estimate']['cost'], 400)
        self.assertEqual(result['estimate']['input'], 10000)

    def test_independent_ratio_of_sums(self):
        rows = [analysis_interval(segment(i), *pair) for i, pair in enumerate(UNEVEN, 1)]
        self.assertEqual(sum(r['points'] for r in rows), 10)
        self.assertEqual(sum(r['delta']['cost'] for r in rows), 28)
        self.assertEqual(100 * 28 / 10, 280)
        self.assertEqual(sum(estimate(*p)['estimate']['cost'] for p in UNEVEN) / 2, 600)

    def test_boundaries_and_partial_fixture(self):
        self.assertFalse(analysis_interval(segment(), *RESET)['included'])
        self.assertEqual(sum(analysis_interval(segment(), *p)['duration'] for p in PAUSE), 200)
        zero = analysis_interval(segment(), *MIDNIGHT[:2])
        self.assertTrue(zero['included'])
        self.assertEqual((zero['points'], zero['delta']['cost']), (0, 2))
        result = estimate(*PARTIAL)
        self.assertEqual(result['priced_coverage'], 50)
        self.assertEqual(result['estimate']['cost'], 200)
        self.assertIn('partial pricing', result['quality'])
