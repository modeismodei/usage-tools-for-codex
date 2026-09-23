import argparse,csv,json,os,pathlib,subprocess,sys,time
from .common import connect,get,put,event,data_path,fingerprint,ensure_run,SCHEMA_VERSION
from .usage import load_prices,index,aggregate,compact
from .estimate import report
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

def text_report(db,c):
    data=report(db,c);s=get(db,'status',{})
    print(f"Tracker: {s.get('phase','not started')} | weekly left: {s.get('left','unknown')}%")
    if s.get('error'):print('Error: '+s['error'])
    print('UTC day     API $ / 100%   quota pp   cache %   priced %   label')
    for d in data['daily']:
        print(f"{d['day']}  {d['api_equivalent_per_100']:>12,.2f} {d['points']:>10.2f} {d['cache_share']:>9.1f} {d['priced_coverage']:>10.1f}   {d['label']}")
    if not data['daily']:print('Collecting: no estimable segment yet.')
    return data

def estimator(argv=None):
    p=argparse.ArgumentParser(description='Read-only local Codex allowance estimator. No model turns or agent messages.')
    p.add_argument('action',nargs='?',default='ui',choices=['ui','start','stop','resume','shutdown','status','report','export','prices','migrate','_daemon'])
    p.add_argument('target',nargs='?');p.add_argument('file',nargs='?')
    p.add_argument('--data-dir');p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))
    p.add_argument('--codex-bin',default='codex');p.add_argument('--bucket',default='codex')
    p.add_argument('--prices');p.add_argument('--interval',type=int,default=300)
    p.add_argument('--resolution',type=float,default=1,help='Assumed quota display resolution in percentage points')
    p.add_argument('--min-points',type=float,default=5);p.add_argument('--label',default='single-device')
    p.add_argument('--new-run',action='store_true');p.add_argument('--background',action='store_true')
    p.add_argument('--json',action='store_true');p.add_argument('--output')
    a=p.parse_args(argv);path=data_path(a.data_dir)
    if a.interval<30 or not 0<a.resolution<=100 or not 0<a.min_points<=100:p.error('interval >=30, resolution/min-points in (0,100] required')
    if a.action=='prices':
        if a.target in (None,'path'):print(config_prices(a.prices));return
        if a.target=='validate':
            prices=load_prices(a.file or config_prices(a.prices));print(f"OK: {len(prices['models'])} models; snapshot {fingerprint(prices)[:12]}");return
        if a.target=='import' and a.file:
            prices=load_prices(a.file)
            dest=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',str(pathlib.Path.home()/'.config')))/'codex-limit-tools/prices.json'
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(prices,indent=2)+'\n')
            print(f'Imported {dest}. Active tracking keeps its frozen snapshot.');return
        p.error('Use prices path | prices validate [FILE] | prices import FILE')
    if a.action=='_daemon':daemon(path);return
    # Shutdown must still work against a legacy database while its daemon holds the lock.
    db=connect(path,migrate=a.action not in ('stop','shutdown'))
    try:
        if a.action=='start':
            if a.target!='tracking':p.error('Use start tracking')
            if running(path):
                if a.new_run:p.error('Shutdown the existing daemon before --new-run')
                print('Tracking daemon already exists; attaching without resetting its baseline.')
            else:
                c=get(db,'config')
                if c is None or a.new_run:
                    c={'codex_home':str(pathlib.Path(a.codex_home).expanduser().resolve()),'codex_bin':a.codex_bin,'bucket':a.bucket,
                       'prices':load_prices(config_prices(a.prices)),'interval':a.interval,'resolution':a.resolution,
                       'min_points':a.min_points,'label':a.label,'started_at':time.time()}
                c=ensure_run(db,c)
                put(db,'control',{'paused':False,'shutdown':False});put(db,'status',{'phase':'starting'})
                db.commit();start_process(path);print(f'Tracking started. State: {path}')
            if not a.background and sys.stdin.isatty() and sys.stdout.isatty():
                from .tui import show
                show(path)
        elif a.action=='migrate':print(f'Database schema {SCHEMA_VERSION}; historical observations retained.')
        elif a.action in ('stop','resume','shutdown'):control(db,path,a.action)
        elif a.action in ('status','report','export'):
            c=get(db,'config',{});data=report(db,c);data['status']=get(db,'status',{});data['daemon_running']=running(path)
            if a.action=='export':
                if not a.output:p.error('export requires --output FILE.json or FILE.csv')
                dest=pathlib.Path(a.output).expanduser()
                if dest.suffix.lower()=='.csv':
                    fields=['day','label','price_hash','meter_hash','input_per_100','noncached_per_100','cached_per_100','output_per_100','reasoning_per_100','api_equivalent_per_100','points','segments','input','cached','noncached','output','unpriced_tokens','priced_tokens','cache_share','priced_coverage']
                    with dest.open('w',newline='') as f:
                        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(data['daily'])
                else:dest.write_text(json.dumps(data,indent=2)+'\n')
                print(f'Exported {dest}')
            elif a.json:print(json.dumps(data,indent=2))
            else:
                print('Daemon: '+('running' if data['daemon_running'] else 'offline'))
                text_report(db,c)
        else:
            if not sys.stdin.isatty():text_report(db,get(db,'config',{}));return
            from .tui import show
            show(path)
    finally:db.close()

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
