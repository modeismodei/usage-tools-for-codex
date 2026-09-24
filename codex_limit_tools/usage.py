# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Incremental response-level log index. Never reads prompts into the database."""
import json,math,pathlib,time
from datetime import datetime
from .common import get,put

FIELDS=('input','noncached','cached','writes','output','reasoning','cost','cost_input','cost_cached','cost_output','priced_tokens','unpriced_tokens','responses','untimed_tokens')

def canonical(name,prices):
    if not name:return 'unknown'
    name=str(name).lower().replace('_','-');name=prices.get('aliases',{}).get(name,name)
    if name in prices['models']:return name
    for key in sorted(prices['models'],key=len,reverse=True):
        suffix=name[len(key)+1:] if name.startswith(key+'-') else ''
        # Only a dated snapshot suffix; do not price arbitrary internal variants as public models.
        import re
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',suffix):return key
    return name

def load_prices(path):
    prices=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if not isinstance(prices,dict) or prices.get('schema')!=1 or not isinstance(prices.get('models'),dict) or not prices['models']:
        raise ValueError('Expected price schema 1 with nonempty models')
    if not isinstance(prices.get('name'),str):raise ValueError('Price snapshot needs a name')
    def numeric(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0
    for key in ('long_context_threshold','long_input_multiplier','long_output_multiplier'):
        if not numeric(prices.get(key)):raise ValueError('Invalid pricing setting: '+key)
    for model,p in prices['models'].items():
        if not isinstance(model,str) or not isinstance(p,dict):raise ValueError('Invalid model price entry')
        for key in ('input','cached','output'):
            if not numeric(p.get(key)):raise ValueError('Invalid price: '+model+' '+key)
        if p.get('cache_write') is not None and not numeric(p['cache_write']):raise ValueError('Invalid cache write price')
        if not isinstance(p.get('long_context',False),bool):raise ValueError('long_context must be boolean')
    aliases=prices.get('aliases',{})
    if not isinstance(aliases,dict) or any(not isinstance(k,str) or v not in prices['models'] for k,v in aliases.items()):
        raise ValueError('Aliases must map to known model IDs')
    return prices

def timestamp(obj,p):
    value=obj.get('timestamp') or p.get('timestamp')
    try:
        if isinstance(value,(int,float)):return float(value) if math.isfinite(value) else None
        return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,AttributeError):return None

def index(db,home):
    home=str(pathlib.Path(home).expanduser().resolve())
    previous=get(db,'indexed_codex_home')
    if previous and previous!=home:raise ValueError('This database indexes another CODEX_HOME; use a separate --data-dir')
    put(db,'indexed_codex_home',home)
    roots=[pathlib.Path(home)/'sessions',pathlib.Path(home)/'archived_sessions']
    paths=sorted({p.resolve() for root in roots if root.exists() for p in root.rglob('rollout-*.jsonl')})
    stats={'files':len(paths),'new_responses':0,'duplicates':0,'foreign':0,'invalid':0,'unsupported_token_count':0,'changed_files':0}
    revision=get(db,'mapping_revision',0)
    for path in paths:
        try:
            st=path.stat(); ident=f'{st.st_dev}:{st.st_ino}'
            row=db.execute('SELECT * FROM files WHERE path=?',(str(path),)).fetchone()
            if row and row['identity']==ident and row['mtime']==st.st_mtime_ns and row['offset']==st.st_size:continue
            offset=row['offset'] if row and row['identity']==ident and st.st_size>=row['offset'] else 0
            # A same-length rewrite must be re-read. Append-only logs are the normal case.
            if row and st.st_size==row['offset'] and row['mtime']!=st.st_mtime_ns:offset=0
            thread=row['thread'] if offset else None
            stats['changed_files']+=1
            with path.open('rb') as f:
                f.seek(offset)
                while True:
                    start=f.tell();line=f.readline()
                    if not line:break
                    if not line.endswith(b'\n'):f.seek(start);break
                    try:
                        obj=json.loads(line);p=obj.get('payload') or {};typ=obj.get('type')
                        if not isinstance(p,dict):raise ValueError()
                    except (ValueError,UnicodeError,AttributeError):stats['invalid']+=1;continue
                    if typ=='session_meta':thread=p.get('id') or thread
                    elif typ=='turn_context' and thread and p.get('turn_id') and p.get('model'):
                        existed=db.execute('SELECT 1 FROM responses WHERE thread=? AND turn=? LIMIT 1',(thread,str(p['turn_id']))).fetchone()
                        change=db.execute('INSERT OR IGNORE INTO turns VALUES (?,?,?)',(thread,str(p['turn_id']),str(p['model']))).rowcount
                        if existed and change:revision+=1
                    elif typ=='token_usage_record':
                        rid=p.get('response_id');owner=p.get('thread_id')
                        # Foreign copies must not reserve response IDs before originals are read.
                        if not thread or owner!=thread:stats['foreign']+=1;continue
                        if not isinstance(rid,str) or not rid:stats['invalid']+=1;continue
                        u=p.get('usage') or {}
                        try:
                            vals=[u.get(k,0) or 0 for k in ['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens']]
                            if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in vals):raise ValueError()
                            inp,cached,writes,out,reason=vals
                            if cached+writes>inp or reason>out:raise ValueError()
                        except (ValueError,TypeError,AttributeError):stats['invalid']+=1;continue
                        values=(rid,thread,str(p.get('turn_id') or ''),timestamp(obj,p),*vals,p.get('model') if isinstance(p.get('model'),str) else None)
                        changed=db.execute('INSERT OR IGNORE INTO responses VALUES (?,?,?,?,?,?,?,?,?,?)',values).rowcount
                        stats['new_responses' if changed else 'duplicates']+=1
                    elif typ=='event_msg' and p.get('type')=='token_count':stats['unsupported_token_count']+=1
                offset=f.tell()
            db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)',(str(path),ident,offset,thread,st.st_mtime_ns))
            put(db,'index_progress',{'at':time.time(),'last_file':path.name,'total_files':len(paths)})
            db.commit()
        except OSError as e:
            stats['invalid']+=1
    put(db,'mapping_revision',revision);put(db,'last_index',stats);db.commit()
    return stats

def aggregate(db,prices,since=None,until=None):
    metrics={k:0 for k in FIELDS};metrics['models']={}
    where=[];params=[]
    if since is not None:where.append('r.ts>=?');params.append(since)
    if until is not None:where.append('r.ts<=?');params.append(until)
    sql='''SELECT r.*,m.n,m.model FROM responses r LEFT JOIN
      (SELECT thread,turn,COUNT(*) n,MIN(model) model FROM turns GROUP BY thread,turn) m
      ON r.thread=m.thread AND r.turn=m.turn'''
    if where:sql+=' WHERE '+' AND '.join(where)
    for r in db.execute(sql,params):
        model=canonical(r['direct_model'] or (r['model'] if r['n']==1 else None),prices)
        tokens=r['inp']+r['out'];p=prices['models'].get(model)
        mix=metrics['models'].setdefault(model,{'tokens':0,'cost':0,'responses':0})
        mix['tokens']+=tokens;mix['responses']+=1
        for key,val in [('input',r['inp']),('noncached',r['inp']-r['cached']),('cached',r['cached']),('writes',r['writes']),('output',r['out']),('reasoning',r['reason']),('responses',1)]:metrics[key]+=val
        if r['ts'] is None:metrics['untimed_tokens']+=tokens
        if not p:metrics['unpriced_tokens']+=tokens;continue
        metrics['priced_tokens']+=tokens
        long=p.get('long_context',False) and r['inp']>prices.get('long_context_threshold',272000)
        im=prices.get('long_input_multiplier',2) if long else 1
        om=prices.get('long_output_multiplier',1.5) if long else 1
        ci=((r['inp']-r['cached']-r['writes'])*p['input']+r['writes']*(p.get('cache_write') if p.get('cache_write') is not None else p['input']))*im/1e6
        cc=r['cached']*p['cached']*im/1e6;co=r['out']*p['output']*om/1e6
        for key,val in [('cost',ci+cc+co),('cost_input',ci),('cost_cached',cc),('cost_output',co)]:metrics[key]+=val
        mix['cost']+=ci+cc+co
    return metrics

def subtract(a,b):
    d={k:a.get(k,0)-b.get(k,0) for k in FIELDS};d['models']={}
    for model in a.get('models',{}).keys()|b.get('models',{}).keys():
        vals={k:a.get('models',{}).get(model,{}).get(k,0)-b.get('models',{}).get(model,{}).get(k,0) for k in ('tokens','cost','responses')}
        if vals['tokens'] or vals['cost']:d['models'][model]=vals
    return d

def compact(v):
    for scale,suffix in [(1e9,'B'),(1e6,'M'),(1e3,'K')]:
        if abs(v)>=scale:return f'{v/scale:.2f}{suffix}'
    return f'{v:.0f}'
