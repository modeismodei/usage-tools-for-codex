"""Descriptive endpoint ratios, never an inferred official allowance."""
import json
from .usage import subtract,FIELDS
from .common import stamp

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

def row_snapshot(row):
    return {'ts':row['ts'],'used':row['used'],'metrics':json.loads(row['metrics'])}

def segments(db,config):
    out=[]
    for seg in db.execute('SELECT * FROM segments ORDER BY id'):
        first=db.execute('SELECT * FROM snapshots WHERE segment=? ORDER BY id LIMIT 1',(seg['id'],)).fetchone()
        last=db.execute('SELECT * FROM snapshots WHERE segment=? ORDER BY id DESC LIMIT 1',(seg['id'],)).fetchone()
        if not first:continue
        saved=json.loads(seg['config'])
        e=estimate(row_snapshot(first),row_snapshot(last),saved.get('resolution',1),saved.get('min_points',5))
        e.update(segment=seg['id'],started=first['ts'],ended=last['ts'],day=stamp(first['ts'])[:10],label=seg['label'],price_hash=seg['price_hash'],meter_hash=saved.get('meter_hash','unknown'),reason=seg['reason'])
        out.append(e)
    return out

def report(db,config):
    rows=segments(db,config);daily={}
    for r in rows:
        if not r['estimate']:continue
        key=(r['day'],r['price_hash'],r['label'],r['meter_hash'])
        group=daily.setdefault(key,{'day':r['day'],'label':r['label'],'price_hash':r['price_hash'],'meter_hash':r['meter_hash'],'points':0,'cost':0,'segments':0,'input':0,'cached':0,'noncached':0,'output':0,'reasoning':0,'unpriced_tokens':0,'priced_tokens':0})
        group['points']+=r['points'];group['segments']+=1
        for k in ['cost','input','cached','noncached','output','reasoning','unpriced_tokens','priced_tokens']:group[k]+=r['delta'][k]
    for g in daily.values():
        g['api_equivalent_per_100']=100*g['cost']/g['points']
        for key in ['input','noncached','cached','output','reasoning']:g[key+'_per_100']=100*g[key]/g['points']
        g['cache_share']=100*g['cached']/g['input'] if g['input'] else 0
        g['priced_coverage']=100*g['priced_tokens']/(g['input']+g['output']) if g['input']+g['output'] else 0
    return {'segments':rows,'daily':list(daily.values())}
