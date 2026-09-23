import curses,json,time
from .common import connect,get,put,stamp
from .estimate import report
from .usage import compact
from .tracker import running

def lines_for(status,current,daily,config,width=100,history=False):
    phase=status.get('phase','not started').upper()
    rows=[('Codex limit estimator', 'title'),
          (f"{phase}   |   weekly left: {status.get('left','—')}%   |   sample every {config.get('interval',300)}s",'muted'),
          ('Observed local work / consumed account quota. Reference prices, not a bill.','muted'),('','')]
    if history:
        rows += [('UTC day       API $ / 100%     quota pp    cache %   priced %','title')]
        for d in daily[-15:]:
            rows.append((f"{d['day']}    ${d['api_equivalent_per_100']:>10,.2f}     {d['points']:>7.2f}    {d['cache_share']:>6.1f}    {d['priced_coverage']:>6.1f}",'normal'))
        rows += [('',''),('Groups with different labels or price snapshots remain separate.','muted')]
    elif current:
        e=current.get('estimate')
        rows += [(f"Segment {current['segment']}  |  {current['reason']}",'muted')]
        if e:
            rows += [(f"100% weekly usage ≈ ${e['cost']:,.2f} API equivalent",'highlight')]
            lo,hi=current['cost_rounding_range']
            rows += [(f"Rounding envelope: ${lo:,.2f} — "+(f'${hi:,.2f}' if hi is not None else 'unbounded'),'normal'),
                     (f"Confidence: not quantified   |   priced token coverage: {current['priced_coverage']:.1f}%",'muted'),
                     (f"Evidence: {current['points']:.2f} quota points over {current['duration']/3600:.2f} h   |   {current['quality']}",'normal'),('',''),
                     ('TOKEN TYPE                 OBSERVED DELTA           PER 100%','title')]
            for label,key in [('Input non-cached','noncached'),('Input cached','cached'),('Output','output'),('Reasoning (inside output)','reasoning')]:
                rows.append((f"{label:<28}{compact(current['delta'][key]):>14}{compact(e[key]):>20}",'normal'))
            rows += [('',''),(f"Cache share {current['cache_share']:.1f}%   |   unpriced tokens {compact(current['delta']['unpriced_tokens'])}",'muted')]
            total=current['delta']['input']+current['delta']['output']
            rows += [('MODEL MIX                   TOKEN SHARE      API $ DELTA','title')]
            for model,m in sorted(current['delta']['models'].items(),key=lambda x:-x[1]['tokens'])[:5]:
                rows.append((f"{model[:27]:<28}{100*m['tokens']/total:>10.1f}%{m['cost']:>17.2f}",'normal'))
        else:
            rows += [('Collecting a matched baseline and measurable quota movement…','highlight'),
                     (f"Current segment: {current['points']:.2f} quota points; {current['duration']/60:.0f} minutes",'normal')]
    else:rows += [('Waiting for the first indexed usage + quota sample…','highlight')]
    if status.get('error'):rows += [('',''),('Last error: '+status['error'],'error')]
    rows += [('',''),(f"Workload label: {config.get('label','unlabelled')}",'muted'),
             (f"Price snapshot: {config.get('prices',{}).get('name','—')}",'muted'),
             ('External account activity and billing lag can bias the estimate.','muted')]
    return rows

def show(path):
    db=connect(path)
    def screen(win):
        try:curses.curs_set(0)
        except curses.error:pass
        colors={k:0 for k in ['title','muted','normal','highlight','error']}
        if curses.has_colors():
            curses.start_color()
            try:curses.use_default_colors();bg=-1
            except curses.error:bg=curses.COLOR_BLACK
            for i,(name,color) in enumerate([('title',curses.COLOR_WHITE),('muted',curses.COLOR_WHITE),('highlight',curses.COLOR_CYAN),('error',curses.COLOR_RED)],1):
                curses.init_pair(i,color,bg);colors[name]=curses.color_pair(i)
        win.timeout(700);history=False;cached={};signature=None
        while True:
            status=get(db,'status',{});config=get(db,'config',{})
            last=db.execute('SELECT MAX(id) FROM snapshots').fetchone()[0]
            if last!=signature or not cached:cached=report(db,config);signature=last
            current=cached.get('segments',[])[-1] if cached.get('segments') else None
            if current and status.get('segment')!=current['segment']:current=None
            h,w=win.getmaxyx();win.erase()
            rows=lines_for(status,current,cached.get('daily',[]),config,w,history)
            if w<58:rows=[('Please widen the terminal to at least 58 columns.','error')]
            for y,(text,style) in enumerate(rows[:max(0,h-3)],1):
                try:win.addstr(y,2,text[:max(0,w-4)],colors.get(style,0)|(curses.A_BOLD if style in ['title','highlight'] else curses.A_DIM if style=='muted' else 0))
                except curses.error:pass
            try:
                win.hline(h-3,1,curses.ACS_HLINE,max(0,w-2))
                footer='q detach   s stop/pause   r resume   h history   (tracking survives q)'
                win.addstr(h-2,2,footer[:max(0,w-4)],curses.A_DIM)
            except curses.error:pass
            win.refresh();key=win.getch()
            if key in (ord('q'),27):return
            if key==ord('h'):history=not history
            if key in (ord('s'),ord('r')):
                if running(path):put(db,'control',{'paused':key==ord('s'),'shutdown':False});db.commit()
    try:curses.wrapper(screen)
    finally:db.close()
    print('TUI detached. Tracking continues if the daemon is running. Use status to check.')
