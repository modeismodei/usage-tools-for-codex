import fcntl,json,os,pathlib,signal,time
from .common import connect,get,put,event,stamp,fingerprint
from .usage import index,aggregate
from .quota import QuotaSource

class Collector:
    def __init__(self,db,config,quota=None):
        self.db=db;self.config=config;self.quota=quota or QuotaSource(config['codex_bin'],config['bucket'])
        self.segment=None;self.last=None;self.pending_reason='tracking started/restarted'
        self.mapping=None
    def boundary(self,reason):self.segment=None;self.last=None;self.pending_reason=reason
    def collect(self):
        db=self.db;c=self.config
        stats=index(db,c['codex_home'])
        if not db.execute('SELECT 1 FROM responses LIMIT 1').fetchone():
            raise ValueError('No supported token_usage_record entries indexed; check CODEX_HOME/log format before estimating')
        quota=self.quota.read()
        if quota['at']-time.time()>30 or time.time()-quota['at']>240:raise ValueError('Stale quota observation')
        # Only include timed response records from the start of this configured run.
        metrics=aggregate(db,c['prices'],since=c['started_at'],until=quota['at'])
        revision=get(db,'mapping_revision',0)
        reason=None
        if stats['invalid']:reason='log parse/read error'
        if self.last:
            if quota['account']!=self.last['account'] or quota['plan']!=self.last['plan']:reason='account/plan changed'
            elif quota['used']<self.last['used']-1e-7:reason='quota replenishment/correction'
            elif quota['reset_at']!=self.last['reset_at']:reason='reset deadline changed'
            elif stamp(quota['at'])[:10]!=stamp(self.last['at'])[:10]:reason='UTC day boundary'
            elif quota['at']-self.last['at']>c['interval']*2.5+60:reason='collection gap'
            elif revision!=self.mapping:reason='historical model attribution changed'
            elif quota['used']>self.last['used'] and metrics['input']+metrics['output']==self.last['metrics']['input']+self.last['metrics']['output']:reason='quota moved without local tokens'
        if reason:self.boundary(reason);event(db,'boundary',reason)
        if self.segment is None:
            cursor=db.execute('INSERT INTO segments(started,reason,label,price_hash,config) VALUES (?,?,?,?,?)',
                (quota['at'],self.pending_reason,c['label'],fingerprint(c['prices']),json.dumps({'resolution':c['resolution'],'min_points':c['min_points'],'meter_hash':fingerprint({'account':quota['account'],'plan':quota['plan'],'bucket':quota['bucket'] if 'bucket' in quota else c['bucket']})})))
            self.segment=cursor.lastrowid
        db.execute('INSERT INTO snapshots(segment,ts,used,reset_at,metrics) VALUES (?,?,?,?,?)',
                   (self.segment,quota['at'],quota['used'],quota['reset_at'],json.dumps(metrics)))
        self.last={**quota,'metrics':metrics};self.mapping=revision
        put(db,'status',{'phase':'tracking','sample_at':quota['at'],'left':quota['left'],'segment':self.segment,
                         'next_sample':time.time()+c['interval'],'index':stats,'error':None})
        db.commit()

def daemon(path):
    os.umask(0o077);db=connect(path)
    lock=open(path/'daemon.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    config=get(db,'config')
    if not config:raise RuntimeError('Start tracking first')
    os.environ['CODEX_HOME']=config['codex_home']
    put(db,'daemon',{'pid':os.getpid(),'started':time.time()});db.commit()
    alive=True
    def stop(sig,frame):
        nonlocal alive
        alive=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    collector=Collector(db,config);due=0;paused=False;failures=0
    try:
        while alive:
            control=get(db,'control',{'paused':False,'shutdown':False})
            if control.get('shutdown'):break
            if control.get('paused'):
                if not paused:
                    collector.boundary('manual pause/resume');collector.quota.close()
                    previous=get(db,'status',{})
                    put(db,'status',{**previous,'phase':'paused'});event(db,'pause','Tracking paused; boundary interval excluded');db.commit()
                paused=True;time.sleep(.25);continue
            if paused:due=0;paused=False
            if time.monotonic()>=due:
                try:
                    put(db,'status',{**get(db,'status',{}),'phase':'sampling','error':None});db.commit()
                    collector.collect();failures=0
                except Exception as exc:
                    collector.boundary('error/recovery gap');collector.quota.close();failures+=1
                    put(db,'status',{**get(db,'status',{}),'phase':'error','error':str(exc)[:240]})
                    event(db,'error',str(exc)[:240]);db.commit()
                due=time.monotonic()+config['interval']*min(4,2**failures)
            time.sleep(.25)
    finally:
        collector.quota.close()
        put(db,'status',{**get(db,'status',{}),'phase':'offline'});put(db,'daemon',None);db.commit()
        lock.close();db.close()

def running(path):
    path.mkdir(parents=True,exist_ok=True)
    with open(path/'daemon.lock','a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return False
        except BlockingIOError:return True
