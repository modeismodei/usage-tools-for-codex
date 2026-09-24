# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
import json,math,os,pathlib,signal,time,uuid
from .common import connect,get,put,event,stamp,fingerprint,daemon_lock,ensure_run,regular_private_path
from .platform_io import WINDOWS, lock_file, unlock_file
from .common import private_open
from .usage import index,aggregate
from .quota import QuotaSource

CHECKPOINT_TIMEOUT = 90


def checkpoint_record(db, request_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='checkpoints'").fetchone():
        raise ValueError('Checkpoints require migration and an updated daemon; shutdown, migrate, then resume')
    row = db.execute('SELECT * FROM checkpoints WHERE id=?', (request_id,)).fetchone()
    if not row:
        raise ValueError('Unknown checkpoint request ID')
    result=dict(row)
    if row['snapshot_id'] is not None:
        snapshot=db.execute('SELECT id,segment,ts,used FROM snapshots WHERE id=?',(row['snapshot_id'],)).fetchone()
        result['snapshot']={**dict(snapshot),'remaining':100-snapshot['used']} if snapshot else None
    return result


def request_checkpoint(db, path, timeout=CHECKPOINT_TIMEOUT):
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError('Checkpoint timeout must be in (0,300] seconds')
    if not running(path):
        raise ValueError('Daemon is absent; checkpoint does not start a collector')
    if db.execute('PRAGMA user_version').fetchone()[0] < 2:
        raise ValueError('Checkpoints require migration and an updated daemon; shutdown, migrate, then resume')
    busy = db.execute('PRAGMA busy_timeout').fetchone()[0]
    db.execute(f'PRAGMA busy_timeout={max(1, int(min(timeout, 1)*1000))}')
    requested = time.time()
    try:
        db.execute('BEGIN IMMEDIATE')
        control = get(db, 'control', {})
        daemon_info = get(db, 'daemon', {}) or {}
        if control.get('paused') or get(db, 'status', {}).get('phase') == 'paused':
            raise ValueError('Daemon is paused; checkpoint will not resume it')
        if control.get('shutdown'):
            raise ValueError('Daemon shutdown is pending')
        if not daemon_info.get('checkpoint_protocol') or not daemon_info.get('instance_id'):
            raise ValueError('Running daemon does not support checkpoints; shutdown and resume the updated package')
        db.execute("UPDATE checkpoints SET status='error',error='request expired before sampling' WHERE status='pending' AND expires<=?", (requested,))
        if db.execute("SELECT 1 FROM checkpoints WHERE status IN ('pending','sampling')").fetchone():
            raise ValueError('A checkpoint is already pending; wait for its acknowledgement')
        request_id = str(uuid.uuid4())
        db.execute('INSERT INTO checkpoints VALUES (?,?,?,?,?,NULL,NULL)',
                   (request_id, requested, requested+timeout, daemon_info['instance_id'], 'pending'))
        db.commit()
        return checkpoint_record(db, request_id)
    except BaseException:
        db.rollback()
        raise
    finally:
        db.execute(f'PRAGMA busy_timeout={busy}')


def wait_checkpoint(db, path, request_id, timeout=CHECKPOINT_TIMEOUT):
    deadline = time.monotonic()+timeout
    while True:
        row = checkpoint_record(db, request_id)
        if row['status'] == 'complete':
            return row
        if row['status'] == 'error':
            raise ValueError(f"Checkpoint {request_id} failed: {row['error']}")
        if not running(path):
            raise ValueError(f'Checkpoint {request_id}: daemon exited before acknowledgement; no retry')
        remaining = min(deadline-time.monotonic(), row['expires']-time.time())
        if remaining <= 0:
            raise TimeoutError(f'Checkpoint {request_id} timed out; no retry. Inspect with checkpoint --request-id {request_id}')
        time.sleep(min(.1, remaining))


def reject_checkpoints(db, reason):
    db.execute("UPDATE checkpoints SET status='error',error=? WHERE status IN ('pending','sampling')", (reason,))
    db.commit()


def claim_checkpoint(db, instance):
    """Only the lock-owning daemon calls this; a claimed request is never replayed."""
    db.execute('BEGIN IMMEDIATE')
    control = get(db, 'control', {})
    if control.get('paused') or control.get('shutdown'):
        reject_checkpoints(db, 'pause or shutdown requested before sampling')
        return None
    db.execute("UPDATE checkpoints SET status='error',error='expired or daemon restarted' "
               "WHERE status='pending' AND (expires<=? OR daemon_instance!=?)", (time.time(), instance))
    row = db.execute("SELECT id FROM checkpoints WHERE status='pending' ORDER BY requested,id LIMIT 1").fetchone()
    if row:
        db.execute("UPDATE checkpoints SET status='sampling' WHERE id=?", (row['id'],))
    db.commit()
    return row['id'] if row else None

class Collector:
    def __init__(self,db,config,quota=None):
        self.db=db;self.config=ensure_run(db,config);self.quota=quota or QuotaSource(config['codex_bin'],config['bucket'])
        self.segment=None;self.last=None;self.pending_reason='tracking started/restarted'
        self.mapping=None
    def boundary(self,reason):self.segment=None;self.last=None;self.pending_reason=reason
    def collect(self, checkpoint_id=None):
        db=self.db;c=self.config
        stats=index(db,c['codex_home'])
        if stats['invalid']:
            raise ValueError('Log parse/read error; a fresh baseline is required after recovery')
        if not db.execute('SELECT 1 FROM responses LIMIT 1').fetchone():
            raise ValueError('No supported token_usage_record entries indexed; check CODEX_HOME/log format before estimating')
        quota=self.quota.read()
        if quota['at']-time.time()>30 or time.time()-quota['at']>240:raise ValueError('Stale quota observation')
        # Only include timed response records from the start of this configured run.
        metrics=aggregate(db,c['prices'],since=c['started_at'],until=quota['at'])
        revision=get(db,'mapping_revision',0)
        reason=None
        if self.last:
            if quota['account']!=self.last['account'] or quota['plan']!=self.last['plan']:reason='account/plan changed'
            elif quota['used']<self.last['used']-1e-7:reason='quota replenishment/correction'
            elif quota['reset_at']!=self.last['reset_at']:reason='reset deadline changed'
            elif quota['at']-self.last['at']>c['interval']*2.5+60:reason='collection gap'
            elif quota['at']<=self.last['at']:reason='non-increasing observation time'
            elif revision!=self.mapping:reason='historical model attribution changed'
            elif quota['used']>self.last['used'] and metrics['input']+metrics['output']==self.last['metrics']['input']+self.last['metrics']['output']:reason='quota moved without local tokens'
        if reason:self.boundary(reason);event(db,'boundary',reason)
        if self.segment is None:
            cursor=db.execute('INSERT INTO segments(started,reason,label,price_hash,config,run_id) VALUES (?,?,?,?,?,?)',
                (quota['at'],self.pending_reason,c['label'],fingerprint(c['prices']),json.dumps({'resolution':c['resolution'],'min_points':c['min_points'],'interval':c['interval'],'meter_hash':fingerprint({'account':quota['account'],'plan':quota['plan'],'bucket':quota['bucket'] if 'bucket' in quota else c['bucket']})}),c['run_id']))
            self.segment=cursor.lastrowid
        cursor=db.execute('INSERT INTO snapshots(segment,ts,used,reset_at,metrics) VALUES (?,?,?,?,?)',
                          (self.segment,quota['at'],quota['used'],quota['reset_at'],json.dumps(metrics)))
        snapshot_id=cursor.lastrowid
        if checkpoint_id:
            db.execute("UPDATE checkpoints SET status='complete',snapshot_id=? WHERE id=? AND status='sampling'",
                       (snapshot_id,checkpoint_id))
        self.last={**quota,'metrics':metrics};self.mapping=revision
        put(db,'status',{'phase':'tracking','sample_at':quota['at'],'left':quota['left'],'segment':self.segment,'snapshot_id':snapshot_id,
                         'next_sample':time.time()+c['interval'],'index':stats,'error':None})
        db.commit()
        return snapshot_id

def daemon(path):
    os.umask(0o077)
    with daemon_lock(path):
        db=connect(path,lock_held=True)
        try:_daemon_loop(path,db)
        finally:db.close()

def _daemon_loop(path,db):
    config=get(db,'config')
    if not config:raise RuntimeError('Start tracking first')
    os.environ['CODEX_HOME']=config['codex_home']
    instance=str(uuid.uuid4())
    reject_checkpoints(db,'daemon restarted before acknowledgement; request was not replayed')
    put(db,'daemon',{'pid':os.getpid(),'started':time.time(),'instance_id':instance,'checkpoint_protocol':1});db.commit()
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
                reject_checkpoints(db,'daemon is paused')
                if not paused:
                    collector.boundary('manual pause/resume');collector.quota.close()
                    previous=get(db,'status',{})
                    put(db,'status',{**previous,'phase':'paused'});event(db,'pause','Tracking paused; boundary interval excluded');db.commit()
                paused=True;time.sleep(.25);continue
            if paused:due=0;paused=False
            request_id=claim_checkpoint(db,instance)
            # A control request can arrive between the loop read and the claim.
            control=get(db,'control',{})
            if control.get('paused') or control.get('shutdown'):
                reject_checkpoints(db,'pause or shutdown requested before sampling')
                continue
            if request_id or time.monotonic()>=due:
                try:
                    put(db,'status',{**get(db,'status',{}),'phase':'sampling','error':None});db.commit()
                    collector.collect(request_id);failures=0
                except Exception as exc:
                    db.rollback()
                    collector.boundary('error/recovery gap');collector.quota.close();failures+=1
                    if request_id:
                        db.execute("UPDATE checkpoints SET status='error',error=? WHERE id=?",(str(exc)[:240],request_id))
                    put(db,'status',{**get(db,'status',{}),'phase':'error','error':str(exc)[:240]})
                    event(db,'error',str(exc)[:240]);db.commit()
                due=time.monotonic()+config['interval']*min(4,2**failures)
            time.sleep(.25)
    finally:
        collector.quota.close()
        reject_checkpoints(db,'daemon stopped before acknowledgement')
        put(db,'status',{**get(db,'status',{}),'phase':'offline'});put(db,'daemon',None);db.commit()

def running(path):
    regular_private_path(path/'daemon.lock')
    if not (path/'daemon.lock').exists():return False
    try:
        stream = private_open(path/'daemon.lock', 'rb') if WINDOWS else open(path/'daemon.lock', 'r')
    except FileNotFoundError:
        return False
    with stream:
        try:
            lock_file(stream)
        except BlockingIOError:
            return True
        unlock_file(stream)
        return False
