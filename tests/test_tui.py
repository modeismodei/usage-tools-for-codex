# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
import unittest

from codex_limit_tools.estimate import analyze_history, segment_summaries
from codex_limit_tools.tui import lines_for, run_analysis
from analysis_fixtures import PARTIAL, UNEVEN
from test_analysis import history


class AggregateTUI(unittest.TestCase):
    def test_run_view_matches_shared_cli_analysis(self):
        source = history(*UNEVEN)
        config = dict(run_id='run-a', interval=300, label='synthetic')
        data = run_analysis(source, config)
        self.assertEqual(data, analyze_history(source, run_ids=['run-a']))
        rows = lines_for({}, segment_summaries(source)[-1], [], config,
                         view='run', run_groups=data['groups'])
        text = '\n'.join(row[0] for row in rows)
        self.assertIn('$280.00', text)
        self.assertIn('10.00 quota points', text)
        self.assertIn('run-a', text)
        self.assertIn('Rounding envelope', text)

    def test_partial_and_multiple_compatibility_groups(self):
        source = history(PARTIAL, UNEVEN[0])
        source[1]['config']['meter_hash'] = 'different'
        config = dict(run_id='run-a')
        data = run_analysis(source, config)
        self.assertEqual(len(data['groups']), 2)
        partial_index = next(i for i, g in enumerate(data['groups']) if g['partial_pricing'])
        rows = lines_for({}, None, [], config, view='run',run_groups=data['groups'],group_index=partial_index)
        self.assertIn('partial pricing', '\n'.join(r[0] for r in rows))
        self.assertIsNone(run_analysis(source, {}))
