import copy
import unittest
from codex_limit_tools.estimate import analysis_interval, analyze_history, estimate, parse_time
from analysis_fixtures import LARGE, UNEVEN, RESET, PAUSE, MIDNIGHT, PARTIAL, segment, snapshot


def history(*pairs):
    return [{**segment(i), 'snapshots': list(pair)} for i, pair in enumerate(pairs, 1)]


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


class Aggregation(unittest.TestCase):
    def test_ratio_of_sums_and_disjoint_rounding(self):
        result = analyze_history(history(*UNEVEN))
        group = result['groups'][0]
        self.assertEqual(group['estimate']['cost'], 280)
        self.assertEqual(group['quota_rounding_error_points'], 2)
        self.assertEqual(group['cost_rounding_range'], [2800/12, 2800/8])
        self.assertEqual(group['source_segment_count'], 2)
        self.assertEqual(group['included_interval_count'], 2)

    def test_shared_endpoint_uncertainty_cancels(self):
        group = analyze_history(history(MIDNIGHT))['groups'][0]
        self.assertEqual(group['points'], 2)
        self.assertEqual(group['delta']['cost'], 8)
        self.assertEqual(group['quota_rounding_error_points'], 1)
        self.assertEqual(group['cost_rounding_range'], [800/3, 800])
        self.assertEqual(len(group['endpoints']), 1)

    def test_unbounded_upper_and_partial_prices(self):
        group = analyze_history(history(UNEVEN[0]))['groups'][0]
        self.assertIsNone(group['cost_rounding_range'][1])
        group = analyze_history(history(PARTIAL))['groups'][0]
        self.assertEqual(group['priced_coverage'], 50)
        self.assertTrue(group['partial_pricing'])
        self.assertEqual(group['delta']['unpriced_tokens'], 100)
        self.assertEqual(group['estimate']['input'], 2000)

    def test_zero_movement_day_contributes_to_overall(self):
        observations = [snapshot(1, 86000, 10), snapshot(2, 86200, 10, 2, 100),
                        snapshot(3, 86500, 12, 8, 400)]
        source = history(observations)
        days = analyze_history(source, group_by='day')['groups']
        self.assertEqual([g['day'] for g in days], ['1970-01-01', '1970-01-02'])
        self.assertIsNone(days[0]['estimate'])
        self.assertEqual(days[0]['delta']['cost'], 2)
        self.assertEqual(days[1]['duration'], 300)
        total = analyze_history(source)['groups'][0]
        self.assertEqual(sum(g['delta']['cost'] for g in days), total['delta']['cost'])
        self.assertEqual(sum(g['points'] for g in days), total['points'])
        self.assertEqual(sum(g['duration'] for g in days), total['duration'])

    def test_reset_pause_and_legacy_midnight_are_excluded(self):
        reset = analyze_history(history(RESET))
        self.assertFalse(reset['estimable'])
        self.assertIn('replenishment', reset['excluded_intervals'][0]['exclusion_reason'])
        for reason in ('manual pause/resume', 'UTC day boundary'):
            source = history(*PAUSE)
            source[1]['reason'] = reason
            result = analyze_history(source)
            self.assertEqual(result['groups'][0]['points'], 3)
            self.assertEqual(result['groups'][0]['delta']['cost'], 6)
            self.assertEqual(result['excluded_duration'], 300)
            self.assertEqual(result['excluded_intervals'][0]['exclusion_reason'], reason)

    def test_filters_intersect_and_duplicate_ids_do_not_multiply(self):
        source = history(*UNEVEN)
        result = analyze_history(source, run_ids=['run-a', 'run-a'], segment_ids=[1, 1, 2],
                                 label='synthetic', start=400, end=1300)
        self.assertEqual(result['groups'][0]['estimate']['cost'], 280)
        self.assertEqual(result['selection']['uncovered_start_seconds'], 100)
        self.assertEqual(result['selection']['uncovered_end_seconds'], 100)
        self.assertEqual(result['selection']['effective_start']['snapshot_id'], 3)
        self.assertFalse(analyze_history(source, label='different')['estimable'])
        # The end is exclusive: do not import an outside observation to make a ratio.
        self.assertFalse(analyze_history(source, segment_ids=[1], end=800)['estimable'])

    def test_separate_prices_meters_labels_and_runs(self):
        for key in ('price_hash', 'meter_hash', 'label'):
            source = history(*UNEVEN)
            if key == 'meter_hash':source[1]['config'][key] = 'different'
            else:source[1][key] = 'different'
            self.assertEqual(len(analyze_history(source, group_by='overall', across_runs=True)['groups']), 2)
        source = history(*UNEVEN)
        source[1]['run_id'] = 'run-b'
        self.assertEqual(len(analyze_history(source, group_by='overall')['groups']), 2)
        group = analyze_history(source, group_by='overall', across_runs=True)['groups'][0]
        self.assertEqual(group['source_run_ids'], ['run-a', 'run-b'])
        self.assertEqual(group['estimate']['cost'], 280)
        for s in source:s['run_id'] = None
        self.assertEqual(len(analyze_history(source)['groups']), 2)

    def test_invalid_selectors_and_counters(self):
        source = history(LARGE)
        for filters in (dict(run_ids=['missing']), dict(segment_ids=[999]),
                        dict(start=2, end=1), dict(across_runs=True)):
            with self.assertRaises(ValueError):analyze_history(source, **filters)
        source = copy.deepcopy(source)
        source[0]['snapshots'][-1]['metrics']['cost'] = -1
        result = analyze_history(source)
        self.assertFalse(result['estimable'])
        self.assertIn('invalid counters', result['excluded_intervals'][0]['exclusion_reason'])

    def test_timezone_and_date_selection(self):
        self.assertEqual(parse_time('1970-01-01'), 0)
        self.assertEqual(parse_time('1970-01-01', end=True), 86400)
        self.assertEqual(parse_time('1970-01-01T01:00:00+01:00'), 0)
        self.assertEqual(parse_time('1970-01-01T00:00:00Z'), 0)
        with self.assertRaises(ValueError):parse_time('1970-01-01T00:00:00')

    def test_more_than_one_cycle_is_an_aggregate_equivalent(self):
        source = history([snapshot(1, 1, 0), snapshot(2, 2, 70, 70, 700)],
                         [snapshot(3, 3, 0), snapshot(4, 4, 70, 140, 1400)])
        group = analyze_history(source)['groups'][0]
        self.assertEqual(group['points'], 140)
        self.assertEqual(group['kind'], 'aggregate equivalent')
        self.assertEqual(group['estimate']['cost'], 150)

    def test_unknown_pricing_coverage(self):
        source = copy.deepcopy(history(LARGE))
        source[0]['snapshots'][-1]['metrics']['priced_tokens'] = 0
        group = analyze_history(source)['groups'][0]
        self.assertIsNone(group['priced_coverage'])
        self.assertTrue(group['partial_pricing'])
        self.assertFalse(group['coverage_known'])

    def test_checkpoint_endpoint_ids_select_exact_observations(self):
        result = analyze_history(history(MIDNIGHT), snapshot_from=14, snapshot_to=15)
        self.assertEqual(result['groups'][0]['delta']['cost'], 6)
        self.assertEqual(result['selection']['effective_start']['snapshot_id'], 14)
        for a, b in ((14, None), (15, 14), (0, 15), (14, 999)):
            with self.assertRaises(ValueError):
                analyze_history(history(MIDNIGHT), snapshot_from=a, snapshot_to=b)


class QuotaRanges(unittest.TestCase):
    def select(self, source, **options):
        return analyze_history(source, remaining_from=73, remaining_to=40, **options)

    def test_exact_and_skipped_thresholds_use_recorded_endpoints(self):
        exact = self.select(history(LARGE))
        self.assertEqual(exact['range_candidates'][0]['status'], 'complete')
        self.assertEqual(exact['groups'][0]['estimate']['cost'], 400)
        source = history([snapshot(1, 100, 26), snapshot(2, 200, 28, 8, 200),
                          snapshot(3, 300, 59, 132, 3300), snapshot(4, 400, 61, 140, 3500)])
        result = self.select(source)
        candidate = result['range_candidates'][0]
        self.assertEqual((candidate['start']['remaining'], candidate['end']['remaining']), (72, 39))
        self.assertEqual((candidate['start']['snapshot_id'], candidate['end']['snapshot_id']), (2, 4))
        self.assertEqual(result['groups'][0]['estimate']['cost'], 400)

    def test_unfinished_partial_and_missing_start(self):
        source = history([snapshot(1, 100, 27), snapshot(2, 200, 50, 92, 2300)])
        result = self.select(source)
        self.assertFalse(result['estimable'])
        self.assertEqual(result['range_candidates'][0]['status'], 'end_not_reached')
        result = self.select(source, allow_partial=True)
        self.assertEqual(result['range_candidates'][0]['status'], 'partial')
        self.assertTrue(result['groups'][0]['partial_selection'])
        self.assertEqual(result['groups'][0]['estimate']['cost'], 400)
        source = history([snapshot(1, 100, 28), snapshot(2, 200, 61, 132, 3300)])
        result = self.select(source, allow_partial=True)
        self.assertFalse(result['estimable'])
        self.assertEqual(result['range_candidates'][0]['status'], 'start_not_recorded')

    def test_repeated_cycles_remain_candidates_and_never_bridge_reset(self):
        source = history(LARGE, [snapshot(3, 500, 27), snapshot(4, 800, 60, 66, 3300)])
        result = self.select(source)
        self.assertEqual(len(result['groups']), 2)
        self.assertEqual([g['estimate']['cost'] for g in result['groups']], [400, 200])
        self.assertEqual(len(self.select(source, segment_ids=[2])['groups']), 1)
        source = history([snapshot(1, 100, 27), snapshot(2, 200, 40, 52, 1300)],
                         [snapshot(3, 300, 10), snapshot(4, 400, 60, 200, 5000)])
        # First cycle is unfinished; the second has a witnessed start crossing
        # which skips both thresholds in one observation, not a measured interval.
        self.assertFalse(self.select(source)['estimable'])

    def test_range_validation_and_no_synthetic_end(self):
        for a, b in ((101, 40), (40, 73), (73, -1), (40, 40), (None, 40), (float('nan'), 40)):
            with self.assertRaises(ValueError):
                analyze_history(history(LARGE), remaining_from=a, remaining_to=b)
        result = self.select(history([snapshot(1, 100, 20), snapshot(2, 200, 70, 200, 5000)]))
        self.assertFalse(result['estimable'])
        self.assertEqual(result['range_candidates'][0]['status'], 'thresholds_skipped_in_one_observation')
