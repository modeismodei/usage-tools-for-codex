"""Rendering helpers that never read quota or change tracking state."""
from .common import stamp
from .usage import FIELDS, compact

DAILY_CSV_FIELDS = ['day','label','price_hash','meter_hash','input_per_100','noncached_per_100',
                    'cached_per_100','output_per_100','reasoning_per_100','api_equivalent_per_100',
                    'points','segments','input','cached','noncached','output','unpriced_tokens',
                    'priced_tokens','cache_share','priced_coverage']


def value(number, digits=2):
    return f'{number:,.{digits}f}' if number is not None else 'n/a'


def analysis_lines(data):
    rows = ['Descriptive aggregate equivalents per 100 quota points']
    selection = data['selection']
    for side in ('start', 'end'):
        requested = selection['requested_'+side]
        effective = selection['effective_'+side]
        rows.append(f"{side.title()}: requested {stamp(requested) if requested is not None else 'open'}; "
                    + (f"observed {stamp(effective['ts'])}, snapshot {effective['snapshot_id']}" if effective else 'no observation'))
    rows.append(f"Uncovered edges (seconds): start {value(selection['uncovered_start_seconds'])}, "
                f"end {value(selection['uncovered_end_seconds'])}")
    for candidate in data['range_candidates']:
        rows.append(f"Range segment {candidate['source_segment_id']}: "
                    f"{candidate['requested_remaining_from']:g}% -> {candidate['requested_remaining_to']:g}% requested; "
                    + candidate['status'].replace('_', ' '))
        for side in ('start', 'end', 'last_available'):
            endpoint = candidate[side]
            if endpoint:
                rows.append(f"  {side.replace('_',' ')}: {endpoint['remaining']:g}% remaining, snapshot {endpoint['snapshot_id']}")
    for group in data['groups']:
        rows.extend(['', f"Runs: {', '.join(r or 'legacy/unknown' for r in group['source_run_ids']) or 'none'}",
                     f"Segments: {','.join(map(str, group['selected_segment_ids']))} | {group['label']}"
                     + (f" | UTC {group['day']}" if group['day'] else ''),
                     f"Price {group['price_hash']} | meter {group['meter_hash']}",
                     f"Observed {group['points']:.2f} quota pp; {group['included_interval_count']} intervals, "
                     f"{group['source_segment_count']} segments, {group['duration']/3600:.2f} covered hours",
                     group['quality']])
        for span in group['endpoints']:
            rows.append(f"  Segment {span['source_segment_id']}: {span['start']['remaining']:g}% -> "
                        f"{span['end']['remaining']:g}% remaining; snapshots "
                        f"{span['start']['snapshot_id']} -> {span['end']['snapshot_id']}")
        estimate = group['estimate']
        if estimate:
            rows.append(f"API $ / 100%: {estimate['cost']:,.2f}" + (' (partial pricing)' if group['partial_pricing'] else ''))
            bounds = group['cost_rounding_range']
            rows.append(f"Conditional rounding envelope: ${bounds[0]:,.2f} to "
                        + (f'${bounds[1]:,.2f}' if bounds[1] is not None else 'unbounded'))
        rows.append('Metric                 Observed delta       Per 100%')
        for key in ('input', 'noncached', 'cached', 'writes', 'output', 'reasoning'):
            rows.append(f"{key:<22} {compact(group['delta'][key]):>14} {compact(estimate[key]) if estimate else 'n/a':>14}")
        rows.append(f"Priced-token coverage {value(group['priced_coverage'])}%; "
                    f"unpriced {compact(group['delta']['unpriced_tokens'])}; cache share {group['cache_share']:.1f}%")
        rows.append('Observed model mix: ' + ', '.join(f"{k}: {compact(v['tokens'])} tokens" for k, v in sorted(group['delta']['models'].items())))
    if not data['groups']:
        rows.append(data['quality'])
    rows.append(f"Excluded duration: {data['excluded_duration']:.0f} seconds")
    reasons = {}
    for row in data['excluded_intervals']:
        reason = row['exclusion_reason']
        reasons[reason] = reasons.get(reason, 0) + max(0, row['duration'])
    rows.extend(f'  {reason}: {duration:.0f} seconds' for reason, duration in sorted(reasons.items()))
    rows.extend(data['quality_notes'])
    return rows


def analysis_csv_rows(data):
    rows = []
    for group in data['groups']:
        row = {'schema_version': data['schema_version'], **group,
               'selection': data['selection'], 'range_candidates': data['range_candidates'],
               'excluded_intervals': data['excluded_intervals'], 'quality_notes': data['quality_notes']}
        for key in FIELDS:
            row[key] = group['delta'][key]
            row[key+'_per_100'] = group['estimate'][key] if group['estimate'] else None
        rows.append(row)
    return rows
