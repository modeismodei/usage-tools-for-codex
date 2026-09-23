"""Descriptive endpoint ratios, never an inferred official allowance."""
import json,math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from .usage import subtract,FIELDS
from .common import stamp,read_snapshot

EXPORT_SCHEMA_VERSION = 2

def analysis_interval(segment, first, last):
    """Normalize one pair of observed endpoints without filling missing history."""
    saved = segment.get('config', {})
    if isinstance(saved, str):
        saved = json.loads(saved)
    delta = subtract(last['metrics'], first['metrics'])
    points = last['used'] - first['used']
    reason = None
    values = [first['used'], last['used'], first['ts'], last['ts'], *delta.values()]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values if not isinstance(v, dict)):
        reason = 'invalid counters'
    elif not (0 <= first['used'] <= 100 and 0 <= last['used'] <= 100):
        reason = 'invalid quota'
    elif last['ts'] <= first['ts']:
        reason = 'non-increasing observation time'
    elif points < 0:
        reason = 'quota replenishment/correction'
    elif first.get('reset_at') != last.get('reset_at'):
        reason = 'reset deadline changed'
    elif any(delta[k] < -1e-6 for k in FIELDS):
        reason = 'invalid counters'
    elif any(v < -1e-6 or not math.isfinite(v) for mix in delta['models'].values() for v in mix.values()):
        reason = 'historical model attribution changed'
    elif (delta['cached'] > delta['input'] or delta['reasoning'] > delta['output']
          or delta['writes'] > delta['noncached']
          or not math.isclose(delta['noncached'] + delta['cached'], delta['input'], abs_tol=1e-6)):
        reason = 'invalid counters'
    elif saved.get('interval') and last['ts'] - first['ts'] > saved['interval'] * 2.5 + 60:
        reason = 'collection gap'
    def endpoint(snapshot):
        return {'snapshot_id': snapshot['id'], 'ts': snapshot['ts'],
                'used': snapshot['used'], 'remaining': 100 - snapshot['used']}
    return {
        'interval_id': f"{segment['id']}:{first['id']}:{last['id']}",
        'source_segment_id': segment['id'], 'source_run_id': segment.get('run_id'),
        'start': endpoint(first), 'end': endpoint(last),
        'points': points, 'delta': delta, 'duration': last['ts'] - first['ts'],
        'compatibility': {'price_hash': segment['price_hash'],
                          'meter_hash': saved.get('meter_hash', 'unknown'),
                          'label': segment['label']},
        'resolution': saved.get('resolution', 1), 'min_points': saved.get('min_points', 5),
        'included': reason is None, 'exclusion_reason': reason,
    }

def estimate(first,last,resolution=1,min_points=5):
    dp=last['used']-first['used'];d=subtract(last['metrics'],first['metrics'])
    result={'points':dp,'delta':d,'duration':last['ts']-first['ts'],'estimate':None,'quality':'collecting'}
    if dp<=0:return result
    if any(d[k]<-1e-6 for k in FIELDS):result['quality']='invalid counters';return result
    if d['input']+d['output']==0:result['quality']='quota moved without local tokens';return result
    result['estimate']={k:100*d[k]/dp for k in FIELDS}
    # Conditional on each endpoint's rounding error being <= resolution/2.
    # This is a deterministic rounding envelope, NOT a statistical confidence interval.
    result['cost_rounding_range']=[100*d['cost']/(dp+resolution),100*d['cost']/(dp-resolution) if dp>resolution else None]
    result['rounding_relative_percent']=100*resolution/dp
    total=d['input']+d['output'];result['priced_coverage']=100*d['priced_tokens']/total
    result['cache_share']=100*d['cached']/d['input'] if d['input'] else 0
    result['quality']='provisional' if dp<min_points else 'descriptive estimate'
    if d['unpriced_tokens']:result['quality']+='; partial pricing'
    return result

QUALITY_NOTES = [
    'Descriptive aggregate equivalent; observed quota points are not statistical confidence or an official allowance.',
    'Compatibility keys do not establish identical model, effort, cache, context or workload mix.',
    'Conditional rounding bounds exclude reporting lag, other-device consumption, incomplete local logs and workload variation.',
    'A change in API-equivalent estimates alone does not establish a provider quota reduction.',
    'Daily intervals belong to the UTC day of their ending observation; no midnight interpolation.',
]


def parse_time(value, *, end=False):
    """Require a timezone for timestamps; date-only end is next UTC midnight."""
    if value is None:
        return None
    try:
        if len(value) == 10:
            parsed = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            if end:
                parsed += timedelta(days=1)
        else:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('timezone required')
        return parsed.timestamp()
    except (ValueError, OverflowError) as exc:
        raise ValueError('Use an ISO 8601 timestamp with timezone, or YYYY-MM-DD') from exc


def row_snapshot(row):
    result = dict(row)
    result['metrics'] = json.loads(result['metrics'])
    return result


def load_history(db):
    """Read persisted observations only, including original schema databases."""
    with read_snapshot(db):
        history = {}
        for row in db.execute('SELECT * FROM segments ORDER BY id'):
            seg = dict(row)
            seg.setdefault('run_id', None)
            seg['config'] = json.loads(seg['config'])
            seg['snapshots'] = []
            history[seg['id']] = seg
        for row in db.execute('SELECT * FROM snapshots ORDER BY id'):
            if row['segment'] in history:
                history[row['segment']]['snapshots'].append(row_snapshot(row))
        return list(history.values())


def summarize(intervals):
    """Ratio of sums, with one uncertainty term for each uncancelled endpoint."""
    delta = dict.fromkeys(FIELDS, 0)
    delta['models'] = {}
    coefficients = defaultdict(int)
    resolutions = {}
    spans = []
    for row in intervals:
        for key in FIELDS:
            delta[key] += row['delta'][key]
        for name, mix in row['delta']['models'].items():
            target = delta['models'].setdefault(name, dict(tokens=0, cost=0, responses=0))
            for key in target:
                target[key] += mix[key]
        for endpoint, sign in [('start', -1), ('end', 1)]:
            ident = (row['source_segment_id'], row[endpoint]['snapshot_id'])
            coefficients[ident] += sign
            resolutions[ident] = max(resolutions.get(ident, 0), row['resolution'])
        if (spans and spans[-1]['source_segment_id'] == row['source_segment_id']
                and spans[-1]['end']['snapshot_id'] == row['start']['snapshot_id']):
            spans[-1]['end'] = row['end']
        else:
            spans.append({k: row[k] for k in ('source_run_id', 'source_segment_id', 'start', 'end')})
    points = sum(row['points'] for row in intervals)
    error = sum(abs(c) * resolutions[ident] / 2 for ident, c in coefficients.items())
    tokens = delta['input'] + delta['output']
    known = bool(tokens) and math.isclose(delta['priced_tokens'] + delta['unpriced_tokens'], tokens, abs_tol=1e-6)
    partial = bool(delta['unpriced_tokens']) or not known
    estimable = bool(intervals) and points > 0 and tokens > 0
    result = {
        'points': points, 'delta': delta, 'estimate': None,
        'duration': sum(row['duration'] for row in intervals),
        'included_interval_count': len(intervals),
        'source_segment_ids': sorted({row['source_segment_id'] for row in intervals}),
        'source_run_ids': sorted({row['source_run_id'] for row in intervals}, key=lambda x: x or ''),
        'endpoints': spans, 'coverage_known': known, 'partial_pricing': partial,
        'priced_coverage': 100 * delta['priced_tokens'] / tokens if known else None,
        'cache_share': 100 * delta['cached'] / delta['input'] if delta['input'] else 0,
        'quota_rounding_error_points': error,
        'points_rounding_range': [points-error, points+error],
        'cost_rounding_range': None, 'rounding_ranges': None,
        'rounding_relative_percent': 100 * error / points if points > 0 else None,
        'kind': 'aggregate equivalent',
    }
    result['source_segment_count'] = len(result['source_segment_ids'])
    if estimable:
        result['estimate'] = {k: 100 * delta[k] / points for k in FIELDS}
        result['rounding_ranges'] = {
            k: [100 * delta[k] / (points+error),
                100 * delta[k] / (points-error) if points > error else None] for k in FIELDS}
        result['cost_rounding_range'] = result['rounding_ranges']['cost']
        result['quality'] = ('provisional' if points < max(r['min_points'] for r in intervals)
                             else 'descriptive estimate')
    else:
        result['quality'] = ('non-estimable: no valid observation intervals' if not intervals else
                             'non-estimable: zero quota movement' if points <= 0 else
                             'non-estimable: quota moved without local tokens')
    if partial:
        result['quality'] += '; partial pricing' if known else '; pricing coverage unknown'
    return result


def analyze_history(history, *, run_ids=None, segment_ids=None, label=None, start=None,
                    end=None, group_by='run', across_runs=False, known_runs=None):
    """Pure observation selection and aggregation. All selectors intersect."""
    if group_by not in ('run', 'day', 'overall'):
        raise ValueError('group-by must be run, day or overall')
    if across_runs and group_by == 'run':
        raise ValueError('--across-runs requires --group-by overall or day')
    if start is not None and end is not None and start >= end:
        raise ValueError('--from must precede --to')
    run_ids, segment_ids = set(run_ids or []), set(segment_ids or [])
    available_runs = {s.get('run_id') or 'legacy' for s in history} | set(known_runs or [])
    if run_ids - available_runs:
        raise ValueError('Unknown run ID: ' + ', '.join(sorted(run_ids-available_runs)))
    if segment_ids - {s['id'] for s in history}:
        raise ValueError('Unknown segment ID: ' + ', '.join(map(str, sorted(segment_ids-{s['id'] for s in history}))))
    selected, intervals, excluded, endpoints = [], {}, [], []
    for seg in history:
        if run_ids and (seg.get('run_id') or 'legacy') not in run_ids:
            continue
        if segment_ids and seg['id'] not in segment_ids:
            continue
        if label is not None and seg['label'] != label:
            continue
        snapshots = [s for s in seg['snapshots'] if (start is None or s['ts'] >= start)
                     and (end is None or s['ts'] < end)]
        if not snapshots:
            continue
        selected.append(seg['id'])
        selected_ids = {s['id'] for s in snapshots}
        endpoints.append({'source_segment_id': seg['id'], 'source_run_id': seg.get('run_id'),
                          'start': {'snapshot_id': snapshots[0]['id'], 'ts': snapshots[0]['ts'],
                                    'remaining': 100-snapshots[0]['used']},
                          'end': {'snapshot_id': snapshots[-1]['id'], 'ts': snapshots[-1]['ts'],
                                  'remaining': 100-snapshots[-1]['used']}})
        for first, last in zip(seg['snapshots'], seg['snapshots'][1:]):
            if first['id'] not in selected_ids or last['id'] not in selected_ids:
                continue
            row = analysis_interval(seg, first, last)
            intervals[row['interval_id']] = row
    # Boundaries remain excluded, including original midnight segmentation.
    by_id = {s['id']: s for s in history}
    positions = {s['id']: i for i, s in enumerate(history)}
    for before, after in zip(endpoints, endpoints[1:]):
        duration = after['start']['ts'] - before['end']['ts']
        if duration > 0:
            adjacent = positions[after['source_segment_id']] == positions[before['source_segment_id']] + 1
            excluded.append({'source_segment_ids': [before['source_segment_id'], after['source_segment_id']],
                             'start': before['end'], 'end': after['start'], 'duration': duration,
                             'included': False, 'exclusion_reason': (by_id[after['source_segment_id']]['reason'] or 'unknown gap') if adjacent else 'unselected history gap'})
    rows = sorted(intervals.values(), key=lambda r: (r['start']['ts'], r['source_segment_id'], r['start']['snapshot_id']))
    groups = defaultdict(list)
    for row in rows:
        if not row['included']:
            excluded.append(row)
        # Retain an empty group for a selection containing invalid counters.
        compatibility = row['compatibility']
        run = '' if across_runs else row['source_run_id'] or f"legacy:{row['source_segment_id']}"
        day = stamp(row['end']['ts'])[:10] if group_by == 'day' else ''
        key = (day, run, compatibility['price_hash'], compatibility['meter_hash'], compatibility['label'])
        groups[key].append(row)
    results = []
    for key, candidates in sorted(groups.items()):
        result = summarize([r for r in candidates if r['included']])
        result.update(group_by=group_by, day=key[0] or None, run_id=key[1] or None,
                      price_hash=key[2], meter_hash=key[3], label=key[4],
                      excluded_interval_count=sum(not r['included'] for r in candidates))
        if result['excluded_interval_count']:
            result['quality'] += '; invalid or discontinuous intervals excluded'
        result['selected_segment_ids'] = sorted({r['source_segment_id'] for r in candidates})
        results.append(result)
    first = min((e['start'] for e in endpoints), key=lambda e: e['ts'], default=None)
    last = max((e['end'] for e in endpoints), key=lambda e: e['ts'], default=None)
    selection = dict(run_ids=sorted(run_ids), segment_ids=sorted(segment_ids), label=label,
                     requested_start=start, requested_end=end, effective_start=first, effective_end=last,
                     uncovered_start_seconds=max(0, first['ts']-start) if first and start is not None else None,
                     uncovered_end_seconds=max(0, end-last['ts']) if last and end is not None else None,
                     endpoints=endpoints, selected_segment_ids=selected,
                     group_by=group_by, across_runs=across_runs, time_convention='[start, end)')
    included = [r for r in rows if r['included']]
    estimable = any(r['estimate'] is not None for r in results)
    return {'schema_version': EXPORT_SCHEMA_VERSION, 'selection': selection, 'groups': results,
            'intervals': rows, 'excluded_intervals': excluded, 'range_candidates': [],
            'excluded_duration': sum(max(0, r['duration']) for r in excluded),
            'coverage': {'included_interval_count': len(included),
                         'source_segment_count': len({r['source_segment_id'] for r in included}),
                         'covered_duration': sum(r['duration'] for r in included)},
            'estimable': estimable,
            'quality': 'descriptive aggregate equivalent' if estimable else 'non-estimable: insufficient valid matched observations',
            'quality_notes': QUALITY_NOTES}


def analyze(db, **filters):
    with read_snapshot(db):
        has_runs = db.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone()
        known_runs = [r[0] for r in db.execute('SELECT id FROM runs')] if has_runs else []
        return analyze_history(load_history(db), known_runs=known_runs, **filters)


def segment_summaries(history):
    out = []
    for seg in history:
        snapshots = seg['snapshots']
        if not snapshots:
            continue
        intervals = [analysis_interval(seg, a, b) for a, b in zip(snapshots, snapshots[1:])]
        result = summarize([r for r in intervals if r['included']])
        result.update(segment=seg['id'], run_id=seg.get('run_id'), started=snapshots[0]['ts'],
                      ended=snapshots[-1]['ts'], day=stamp(snapshots[0]['ts'])[:10], label=seg['label'],
                      price_hash=seg['price_hash'], meter_hash=seg['config'].get('meter_hash', 'unknown'),
                      reason=seg['reason'], remaining_start=100-snapshots[0]['used'],
                      remaining_end=100-snapshots[-1]['used'],
                      first_snapshot_id=snapshots[0]['id'], last_snapshot_id=snapshots[-1]['id'])
        out.append(result)
    return out


def segments(db, config=None):
    return segment_summaries(load_history(db))


def report(db, config=None):
    with read_snapshot(db):
        history = load_history(db)
        analysis = analyze_history(history, group_by='day', across_runs=True)
        daily = []
        for group in analysis['groups']:
            row = dict(group)
            row.update({k: group['delta'][k] for k in FIELDS})
            row['segments'] = group['source_segment_count']
            row['api_equivalent_per_100'] = group['estimate']['cost'] if group['estimate'] else None
            for key in ('input', 'noncached', 'cached', 'output', 'reasoning'):
                row[key+'_per_100'] = group['estimate'][key] if group['estimate'] else None
            daily.append(row)
        return {'schema_version': EXPORT_SCHEMA_VERSION, 'segments': segment_summaries(history),
                'daily': daily, 'analysis': analysis}
