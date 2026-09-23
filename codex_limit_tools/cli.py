import argparse,csv,json,os,pathlib,subprocess,sys,time
from .common import connect,get,put,event,data_path,fingerprint,ensure_run,SCHEMA_VERSION,read_snapshot,stamp
from .usage import load_prices,index,aggregate,compact
from .estimate import (report, report_history, load_history, segment_summaries, analyze_history,
                       parse_time, EXPORT_SCHEMA_VERSION)
from .render import DAILY_CSV_FIELDS, analysis_lines, analysis_csv_rows
from .tracker import daemon,running
from .quota import QuotaSource

PACKAGE=pathlib.Path(__file__).resolve().parent.parent

def config_prices(path):
    config=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',str(pathlib.Path.home()/'.config')))/'codex-limit-tools/prices.json'
    return pathlib.Path(path).expanduser().resolve() if path else config if config.exists() else PACKAGE/'prices.json'

def start_process(path):
    with (path/'daemon.log').open('ab') as log:
        subprocess.Popen([sys.executable,str(PACKAGE/'codex-limit-estimator'),'_daemon','--data-dir',str(path)],
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def control(db,path,action):
    put(db,'control',{'paused':action=='stop','shutdown':action=='shutdown'});db.commit()
    if action=='resume' and not running(path):
        if not get(db,'config'):raise ValueError('Run start tracking first')
        start_process(path)
    print({'stop':'Pause requested; no new samples until resume.','resume':'Tracking resumed; next sample establishes a fresh baseline.','shutdown':'Daemon shutdown requested; historical data retained.'}[action])

def text_report(db,c,data=None):
    if data is None:
        with read_snapshot(db):
            data=report(db,c);data['status']=get(db,'status',{})
    s=data.get('status',{})
    print(f"Tracker: {s.get('phase','not started')} | weekly left: {s.get('left','unknown')}%")
    if s.get('error'):print('Error: '+s['error'])
    print('UTC day     API $ / 100%   quota pp   cache %   priced %   label')
    for d in data['daily']:
        cost=f"{d['api_equivalent_per_100']:,.2f}" if d['api_equivalent_per_100'] is not None else 'n/a'
        coverage=f"{d['priced_coverage']:.1f}" if d['priced_coverage'] is not None else 'unknown'
        print(f"{d['day']}  {cost:>12} {d['points']:>10.2f} {d['cache_share']:>9.1f} {coverage:>10}   {d['label']}")
    if not data['daily']:print('Collecting: no estimable segment yet.')
    return data

def run_inventory(db, history):
    has_runs = db.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone()
    rows = []
    if has_runs:
        for row in db.execute('SELECT id,started,registered_at,label,price_hash,prices FROM runs ORDER BY started,id'):
            item = dict(row)
            item['prices'] = json.loads(item['prices'])
            item['segment_count'] = sum(s['run_id'] == item['id'] for s in history)
            rows.append(item)
    legacy = [s for s in history if s['run_id'] is None]
    if legacy:
        rows.append(dict(id='legacy', started=None, registered_at=None, label='legacy/unknown',
                         price_hash=None, prices=None, segment_count=len(legacy)))
    return rows


def selected_history(history, analysis):
    bounds = {e['source_segment_id']: (e['start']['snapshot_id'], e['end']['snapshot_id'])
              for e in analysis['selection']['endpoints']}
    return [{**s, 'snapshots': [r for r in s['snapshots'] if bounds[s['id']][0] <= r['id'] <= bounds[s['id']][1]]}
            for s in history if s['id'] in bounds]


def export_file(dest, data, view):
    if dest.suffix.lower() not in ('.json', '.csv'):
        raise ValueError('Export filename must end in .json or .csv')
    if dest.suffix.lower() == '.json':
        dest.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
        return
    if view == 'daily':
        rows, fields = data['daily'], DAILY_CSV_FIELDS
    else:
        rows = analysis_csv_rows(data) if view == 'analysis' else data[view]
        fields = list(dict.fromkeys(['schema_version'] + [key for row in rows for key in row]))
        if len(fields) == 1:
            fields += ['quality', 'selection', 'range_candidates'] if view == 'analysis' else ['id']
            if view == 'analysis':
                rows = [{k: data[k] for k in fields}]
    with dest.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True, allow_nan=False) if isinstance(v, (dict, list)) else v
                             for k, v in {'schema_version': EXPORT_SCHEMA_VERSION, **row}.items()})


def estimator(argv=None):
    p = argparse.ArgumentParser(description='Read-only local Codex allowance estimator. No model turns or agent messages.')
    p.add_argument('action', nargs='?', default='ui', choices=['ui','start','stop','resume','shutdown','status',
                   'report','export','prices','migrate','runs','segments','analyze','_daemon'])
    p.add_argument('target', nargs='?')
    p.add_argument('file', nargs='?')
    p.add_argument('--data-dir')
    p.add_argument('--codex-home', default=os.environ.get('CODEX_HOME', str(pathlib.Path.home()/'.codex')))
    p.add_argument('--codex-bin', default='codex')
    p.add_argument('--bucket', default='codex')
    p.add_argument('--prices')
    p.add_argument('--interval', type=int, default=300)
    p.add_argument('--resolution', type=float, default=1, help='Assumed quota display resolution in percentage points')
    p.add_argument('--min-points', type=float, default=5)
    p.add_argument('--label')
    p.add_argument('--new-run', action='store_true')
    p.add_argument('--background', action='store_true')
    p.add_argument('--json', action='store_true')
    p.add_argument('--output')
    p.add_argument('--run', action='append', default=[], help='Run UUID or legacy; repeat to select several')
    p.add_argument('--segments', action='append', default=[], help='Comma-separated segment IDs; may be repeated')
    p.add_argument('--from', dest='from_time', help='Inclusive ISO timestamp or UTC date')
    p.add_argument('--to', dest='to_time', help='Exclusive ISO timestamp, or inclusive UTC date')
    p.add_argument('--group-by', choices=['run','day','overall'])
    p.add_argument('--across-runs', action='store_true')
    p.add_argument('--view', choices=['daily','segments','snapshots','analysis'])
    p.add_argument('--remaining-from', type=float)
    p.add_argument('--remaining-to', type=float)
    p.add_argument('--allow-partial', action='store_true')
    a = p.parse_args(argv)
    path = data_path(a.data_dir)
    if a.interval < 30 or not 0 < a.resolution <= 100 or not 0 < a.min_points <= 100:
        p.error('interval >=30, resolution/min-points in (0,100] required')
    if (a.target or a.file) and a.action not in ('start', 'prices'):
        p.error('Unexpected positional arguments')
    if (a.run or a.segments or a.from_time or a.to_time) and a.action not in ('segments','analyze','export'):
        p.error('History selectors require segments, analyze or export')
    if a.view and a.action != 'export':
        p.error('--view requires export')
    analysis_options = (a.group_by or a.across_runs or a.remaining_from is not None
                        or a.remaining_to is not None or a.allow_partial)
    if analysis_options and not (a.action == 'analyze' or a.action == 'export' and a.view == 'analysis'):
        p.error('Grouping and quota-range options require analyze or export --view analysis')
    if a.output and a.action != 'export':
        p.error('--output requires export')
    if a.new_run and a.action != 'start':
        p.error('--new-run requires start tracking')
    if a.label is not None and a.action not in ('start','runs','segments','analyze','export'):
        p.error('--label requires start, runs, segments, analyze or export')
    try:
        ids = [int(part) for item in a.segments for part in item.split(',')]
        if any(i <= 0 for i in ids):raise ValueError()
    except ValueError:
        p.error('--segments requires positive integer IDs separated by commas')
    try:
        filters = dict(run_ids=a.run, segment_ids=ids, label=a.label,
                       start=parse_time(a.from_time), end=parse_time(a.to_time, end=True),
                       group_by=a.group_by or 'run', across_runs=a.across_runs,
                       remaining_from=a.remaining_from, remaining_to=a.remaining_to, allow_partial=a.allow_partial)
    except ValueError as exc:
        p.error(str(exc))
    if a.action == 'prices':
        if a.target in (None, 'path'):
            print(config_prices(a.prices));return
        if a.target == 'validate':
            prices = load_prices(a.file or config_prices(a.prices))
            print(f"OK: {len(prices['models'])} models; snapshot {fingerprint(prices)[:12]}");return
        if a.target == 'import' and a.file:
            prices = load_prices(a.file)
            dest = pathlib.Path(os.environ.get('XDG_CONFIG_HOME', str(pathlib.Path.home()/'.config')))/'codex-limit-tools/prices.json'
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(prices, indent=2)+'\n')
            print(f'Imported {dest}. Active tracking keeps its frozen snapshot.');return
        p.error('Use prices path | prices validate [FILE] | prices import FILE')
    if a.action == '_daemon':
        daemon(path);return
    read_only = a.action in ('runs','segments','analyze','status','report','export')
    if (read_only or a.action in ('ui','stop','resume','shutdown')) and not (path/'tracking.sqlite3').exists():
        raise ValueError('No tracking history; start tracking or choose an existing --data-dir')
    db = connect(path, readonly=read_only, migrate=a.action in ('start','resume','migrate'))
    try:
        if a.action == 'start':
            if a.target != 'tracking' or a.file:p.error('Use start tracking')
            if running(path):
                if a.new_run:p.error('Shutdown the existing daemon before --new-run')
                print('Tracking daemon already exists; attaching without resetting its baseline.')
            else:
                c = get(db, 'config')
                if c is None or a.new_run:
                    c = {'codex_home':str(pathlib.Path(a.codex_home).expanduser().resolve()),
                         'codex_bin':a.codex_bin, 'bucket':a.bucket, 'prices':load_prices(config_prices(a.prices)),
                         'interval':a.interval, 'resolution':a.resolution, 'min_points':a.min_points,
                         'label':a.label if a.label is not None else 'single-device', 'started_at':time.time()}
                c = ensure_run(db, c)
                put(db, 'control', {'paused':False, 'shutdown':False})
                put(db, 'status', {'phase':'starting'})
                db.commit();start_process(path)
                print(f"Tracking started. Run: {c['run_id']} | State: {path}")
            if not a.background and sys.stdin.isatty() and sys.stdout.isatty():
                from .tui import show
                show(path)
        elif a.action == 'migrate':
            print(f'Database schema {SCHEMA_VERSION}; historical observations retained.')
        elif a.action in ('stop','resume','shutdown'):
            control(db, path, a.action)
        elif read_only:
            with read_snapshot(db):
                if a.action in ('status','report'):
                    data = report(db)
                    data['status'] = get(db, 'status', {})
                    data['daemon_running'] = running(path)
                else:
                    history = load_history(db)
                    runs = run_inventory(db, history)
                    if a.action == 'runs':
                        data = {'schema_version':EXPORT_SCHEMA_VERSION,
                                'runs':[r for r in runs if a.label is None or r['label'] == a.label]}
                    else:
                        analysis = analyze_history(history, known_runs=[r['id'] for r in runs], **filters)
                        chosen = selected_history(history, analysis)
                        view = a.view or ('segments' if a.action == 'segments' else 'daily')
                        if a.action == 'analyze' or view == 'analysis':
                            data = analysis
                        elif view == 'segments':
                            data = {'schema_version':EXPORT_SCHEMA_VERSION, 'selection':analysis['selection'],
                                    'segments':segment_summaries(chosen)}
                        elif view == 'snapshots':
                            data = {'schema_version':EXPORT_SCHEMA_VERSION, 'selection':analysis['selection'],
                                    'snapshots':[dict(s, run_id=seg['run_id'], label=seg['label'],
                                                      price_hash=seg['price_hash'], **seg['config'])
                                                 for seg in chosen for s in seg['snapshots']]}
                        else:
                            data = report_history(chosen)
                            data['status'] = get(db, 'status', {})
                            data['daemon_running'] = running(path)
            if a.action == 'export':
                if not a.output:p.error('export requires --output FILE.json or FILE.csv')
                dest = pathlib.Path(a.output).expanduser()
                export_file(dest, data, a.view or 'daily')
                print(json.dumps({'schema_version':EXPORT_SCHEMA_VERSION, 'output':str(dest)}) if a.json else f'Exported {dest}')
            elif a.json:
                print(json.dumps(data, indent=2, allow_nan=False))
            elif a.action == 'analyze':
                print('\n'.join(analysis_lines(data)))
            elif a.action == 'runs':
                print('Run ID                                Segments  UTC start                  Label')
                for r in data['runs']:
                    print(f"{r['id']:<37} {r['segment_count']:>8}  {stamp(r['started']) if r['started'] is not None else 'unknown':<26} {r['label']}")
            elif a.action == 'segments':
                print('Segment  Run ID                                Remaining endpoints  Snapshot IDs')
                for s in data['segments']:
                    print(f"{s['segment']:>7}  {s['run_id'] or 'legacy/unknown':<37} {s['remaining_start']:g}% -> {s['remaining_end']:g}%"
                          f"  {s['first_snapshot_id']} -> {s['last_snapshot_id']} | {s['label']}")
            else:
                print('Daemon: '+('running' if data['daemon_running'] else 'offline'))
                text_report(db, {}, data)
        else:
            if not sys.stdin.isatty():text_report(db, get(db, 'config', {}));return
            from .tui import show
            show(path)
    finally:
        db.close()

def usage(argv=None):
    p=argparse.ArgumentParser(description='Incremental local token totals using an editable JSON price list.')
    p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))
    p.add_argument('--data-dir');p.add_argument('--prices');p.add_argument('--json',action='store_true')
    a=p.parse_args(argv);path=data_path(a.data_dir);db=connect(path)
    try:
        if running(path):
            expected=get(db,'indexed_codex_home') or get(db,'config',{}).get('codex_home')
            if expected and expected!=str(pathlib.Path(a.codex_home).expanduser().resolve()):
                raise ValueError('Active tracker uses another CODEX_HOME; choose a separate --data-dir')
            stats=get(db,'last_index',{});note='Using tracker index as of its latest sample.'
        else:stats=index(db,a.codex_home);note='Local index refreshed.'
        prices=load_prices(config_prices(a.prices));m=aggregate(db,prices)
        if a.json:print(json.dumps({'totals':m,'diagnostics':stats,'prices':prices['name'],'note':note},indent=2));return
        print(f"Sessions indexed: {db.execute('SELECT COUNT(*) FROM files').fetchone()[0]}\n{note}\n")
        for label,key in [('Input total','input'),('  non-cached','noncached'),('  cached','cached'),('Output','output'),('Reasoning (inside output)','reasoning')]:print(f'{label:<28}{m[key]:>18,}')
        print(f"\nAPI equivalent (priced):     ${m['cost']:>17,.2f}\nUnpriced tokens:              {m['unpriced_tokens']:>17,}")
        print(f"\n{'Model':<28}{'Tokens':>12}{'API $':>14}")
        for name,v in sorted(m['models'].items(),key=lambda x:-x[1]['tokens']):print(f"{name[:27]:<28}{compact(v['tokens']):>12}{v['cost']:>14,.2f}")
        print('\nPrices: '+prices['name']+' (reference equivalent; not an invoice)')
        print('Diagnostics: '+json.dumps(stats))
    finally:db.close()

def quota(argv=None):
    p=argparse.ArgumentParser(description='Read account quota without a model turn. Does not control existing watchers.')
    p.add_argument('--codex-bin',default='codex');p.add_argument('--bucket',default='codex');p.add_argument('--json',action='store_true')
    a=p.parse_args(argv);source=QuotaSource(a.codex_bin,a.bucket)
    try:
        q=source.read();print(json.dumps(q,indent=2) if a.json else f"Weekly: {q['left']:g}% left | reset timestamp: {q['reset_at']}")
    finally:source.close()
