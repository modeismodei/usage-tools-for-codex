import curses,json,time
from .common import connect,get,put,stamp,read_snapshot
from .estimate import report_history,load_history,analyze_history
from .usage import compact
from .tracker import running

def run_analysis(history,config):
    run_id=config.get('run_id')
    return analyze_history(history,run_ids=[run_id],known_runs=[run_id]) if run_id else None


def lines_for(status,current,daily,config,width=100,history=False,view='segment',run_groups=None,group_index=0):
    if history:view='history'
    if view=='run':
        if run_groups:
            group_index%=len(run_groups)
            current={**run_groups[group_index],'segment':','.join(map(str,run_groups[group_index]['source_segment_ids'])),
                     'reason':f'current run aggregate; compatibility group {group_index+1}/{len(run_groups)}'}
        else:current=None
    phase=status.get('phase','not started').upper()
    rows=[(f'Codex limit estimator | {view} view', 'title'),
          (f"{phase}   |   weekly left: {status.get('left','—')}%   |   sample every {config.get('interval',300)}s",'muted'),
          ('Observed local work / consumed account quota. Reference prices, not a bill.','muted'),('','')]
    if view=='history':
        rows += [('UTC day       API $ / 100%     quota pp    cache %   priced %','title')]
        for d in daily[-15:]:
            cost=f"{d['api_equivalent_per_100']:,.2f}" if d['api_equivalent_per_100'] is not None else 'n/a'
            coverage=f"{d['priced_coverage']:.1f}" if d['priced_coverage'] is not None else '?'
            rows.append((f"{d['day']}    ${cost:>10}     {d['points']:>7.2f}    {d['cache_share']:>6.1f}    {coverage:>6}  {d['label']}"+(' partial' if d['partial_pricing'] else ''),'normal'))
        rows += [('',''),('Groups with different labels or price snapshots remain separate.','muted')]
    elif current:
        e=current.get('estimate')
        rows += [(f"Segment {current['segment']}  |  {current['reason']}",'muted')]
        if view=='run':rows += [(f"Run: {config.get('run_id','legacy/unknown')}",'muted')]
        if e:
            rows += [(f"Equivalent per 100% ≈ ${e['cost']:,.2f} API"+(' (partial pricing)' if current['partial_pricing'] else ''),'highlight')]
            lo,hi=current['cost_rounding_range']
            rows += [(f"Rounding envelope: ${lo:,.2f} — "+(f'${hi:,.2f}' if hi is not None else 'unbounded'),'normal'),
                     (f"Confidence: not quantified   |   priced token coverage: {current['priced_coverage'] if current['priced_coverage'] is not None else 'unknown'}%",'muted'),
                     (f"Evidence: {current['points']:.2f} quota points over {current['duration']/3600:.2f} h   |   {current['quality']}",'normal'),('',''),
                     ('TOKEN TYPE                 OBSERVED DELTA           PER 100%','title')]
            for label,key in [('Input total','input'),('Input non-cached','noncached'),('Input cached','cached'),('Cache writes (inside input)','writes'),('Output','output'),('Reasoning (inside output)','reasoning')]:
                rows.append((f"{label:<28}{compact(current['delta'][key]):>14}{compact(e[key]):>20}",'normal'))
            rows += [('',''),(f"Cache share {current['cache_share']:.1f}%   |   unpriced tokens {compact(current['delta']['unpriced_tokens'])}",'muted')]
            total=current['delta']['input']+current['delta']['output']
            rows += [('MODEL MIX                   TOKEN SHARE      API $ DELTA','title')]
            for model,m in sorted(current['delta']['models'].items(),key=lambda x:-x[1]['tokens'])[:5]:
                rows.append((f"{model[:27]:<28}{100*m['tokens']/total:>10.1f}%{m['cost']:>17.2f}",'normal'))
        else:
            rows += [(current['quality'],'highlight'),
                     (f"Observed: {current['points']:.2f} quota points; {current['duration']/60:.0f} minutes",'normal'),
                     (f"Local tokens: {compact(current['delta']['input']+current['delta']['output'])}",'normal')]
    else:rows += [('No matched observations for this view yet.','highlight')]
    if status.get('error'):rows += [('',''),('Last error: '+status['error'],'error')]
    rows += [('',''),(f"Workload label: {config.get('label','unlabelled')}",'muted'),
             (f"Price snapshot: {config.get('prices',{}).get('name','—')}",'muted'),
             ('Bounds omit reporting lag, other devices, missing logs and workload variation.','muted')]
    return rows

def show(path):
    db=connect(path,migrate=False)
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
        win.timeout(700);view='segment';cached={};signature=None;group_index=0
        while True:
            with read_snapshot(db):
                status=get(db,'status',{});config=get(db,'config',{})
                last=(db.execute('SELECT MAX(id) FROM snapshots').fetchone()[0],config.get('run_id'))
                if last!=signature or not cached:
                    history=load_history(db);cached=report_history(history);signature=last
                    cached['run_analysis']=run_analysis(history,config)
            current=cached.get('segments',[])[-1] if cached.get('segments') else None
            if current and status.get('segment')!=current['segment']:current=None
            h,w=win.getmaxyx();win.erase()
            groups=(cached.get('run_analysis') or {}).get('groups',[])
            rows=lines_for(status,current,cached.get('daily',[]),config,w,view=view,run_groups=groups,group_index=group_index)
            if w<58:rows=[(f'{view} view | {status.get("phase","offline")}','title'),('Widen terminal for details.','muted')]
            for y,(text,style) in enumerate(rows[:max(0,h-3)],1):
                try:win.addstr(y,2,text[:max(0,w-4)],colors.get(style,0)|(curses.A_BOLD if style in ['title','highlight'] else curses.A_DIM if style=='muted' else 0))
                except curses.error:pass
            try:
                win.hline(h-3,1,curses.ACS_HLINE,max(0,w-2))
                footer='q detach  s pause  r resume  v view  h history  [ ] group'
                if w<58:footer='q detach s pause r resume v view'
                win.addstr(h-2,2,footer[:max(0,w-4)],curses.A_DIM)
            except curses.error:pass
            win.refresh();key=win.getch()
            if key in (ord('q'),27):return
            if key==ord('h'):view='segment' if view=='history' else 'history'
            if key==ord('v'):view={'segment':'run','run':'history','history':'segment'}[view]
            if key in (ord('['),ord(']')) and groups:
                group_index=(group_index+(1 if key==ord(']') else -1))%len(groups)
            if key in (ord('s'),ord('r')):
                if running(path):put(db,'control',{'paused':key==ord('s'),'shutdown':False});db.commit()
    try:curses.wrapper(screen)
    finally:db.close()
    print('TUI detached. Tracking continues if the daemon is running. Use status to check.')
