import fcntl,hashlib,json,os,pathlib,sqlite3,time,uuid
from contextlib import closing,contextmanager

SCHEMA_VERSION = 2

BASE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,identity TEXT,offset INTEGER,thread TEXT,mtime INTEGER);
CREATE TABLE IF NOT EXISTS turns(thread TEXT,turn TEXT,model TEXT,PRIMARY KEY(thread,turn,model));
CREATE TABLE IF NOT EXISTS responses(id TEXT PRIMARY KEY,thread TEXT,turn TEXT,ts REAL,inp INTEGER,cached INTEGER,writes INTEGER,out INTEGER,reason INTEGER,direct_model TEXT);
CREATE INDEX IF NOT EXISTS response_ts ON responses(ts);
CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY,started REAL,reason TEXT,label TEXT,price_hash TEXT,config TEXT);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,segment INTEGER,ts REAL,used REAL,reset_at REAL,metrics TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,detail TEXT);
'''


@contextmanager
def daemon_lock(path):
    """Use the same lock inode as both the original and current collector."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (path / 'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Collector is active. Run codex-limit-estimator shutdown '
                             'with the same --data-dir, wait for Daemon: offline, then retry.') from None
        yield lock


def _migration_v1(db):
    for statement in BASE_SCHEMA.split(';'):
        if statement.strip():
            db.execute(statement)
    db.execute('''CREATE TABLE runs(id TEXT PRIMARY KEY, started REAL, registered_at REAL,
                  label TEXT, price_hash TEXT, prices TEXT, config TEXT)''')
    db.execute('ALTER TABLE segments ADD COLUMN run_id TEXT REFERENCES runs(id)')
    db.execute('CREATE INDEX segment_run ON segments(run_id)')
    db.execute('CREATE INDEX snapshot_segment ON snapshots(segment,id)')


def _migration_v2(db):
    db.execute('''CREATE TABLE checkpoints(id TEXT PRIMARY KEY, requested REAL, expires REAL,
                  daemon_instance TEXT, status TEXT, snapshot_id INTEGER, error TEXT)''')


def _migrate(db, path):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise ValueError(f'Unsupported newer database schema {version}; this package supports {SCHEMA_VERSION}')
    existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
    if existing:
        backup_path = path / f'tracking.sqlite3.backup-v{version}-{time.time_ns()}-{uuid.uuid4().hex[:8]}'
        with closing(sqlite3.connect(backup_path)) as backup:
            db.backup(backup)
        backup_path.chmod(0o600)
    # Do not use executescript: it implicitly commits pending transactions.
    db.execute('BEGIN IMMEDIATE')
    try:
        if version < 1:
            _migration_v1(db)
        if version < 2:
            _migration_v2(db)
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
    except BaseException:
        db.rollback()
        raise

def data_path(value=None):
    return pathlib.Path(value or os.path.join(os.environ.get('XDG_STATE_HOME',str(pathlib.Path.home()/'.local/state')),'codex-limit-estimator')).expanduser().resolve()

def connect(path, *, readonly=False, lock_held=False, migrate=True):
    path=pathlib.Path(path)
    if readonly:
        db=sqlite3.connect((path/'tracking.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    else:
        path.mkdir(parents=True,exist_ok=True,mode=0o700)
        db=sqlite3.connect(path/'tracking.sqlite3',timeout=30)
    db.row_factory=sqlite3.Row
    try:
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version>SCHEMA_VERSION:
            raise ValueError(f'Unsupported newer database schema {version}; this package supports {SCHEMA_VERSION}')
        if readonly:
            db.execute('PRAGMA query_only=ON')
        elif migrate:
            if version<SCHEMA_VERSION:
                if lock_held:_migrate(db,path)
                else:
                    with daemon_lock(path):_migrate(db,path)
            db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=30000')
        return db
    except BaseException:
        db.close()
        raise


@contextmanager
def read_snapshot(db):
    """Pin all queries in a report to one committed SQLite snapshot."""
    nested=db.in_transaction
    if not nested:db.execute('BEGIN')
    try:
        yield db
    finally:
        if not nested:db.rollback()


def ensure_run(db, config):
    """Register only future observations; never guess legacy run membership."""
    config=dict(config)
    if config.get('run_id'):
        if not db.execute('SELECT 1 FROM runs WHERE id=?',(config['run_id'],)).fetchone():
            raise ValueError('Configured run is missing from history')
        return config
    config['run_id']=str(uuid.uuid4())
    db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?)',
               (config['run_id'],config['started_at'],time.time(),config['label'],
                fingerprint(config['prices']),json.dumps(config['prices']),json.dumps(config)))
    put(db,'config',config)
    return config

def get(db,key,default=None):
    row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else default

def put(db,key,value):
    db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,json.dumps(value)))

def event(db,kind,detail):
    db.execute('INSERT INTO events(ts,kind,detail) VALUES (?,?,?)',(time.time(),kind,detail))

def fingerprint(value): return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def stamp(ts):
    from datetime import datetime,timezone
    return datetime.fromtimestamp(ts,timezone.utc).isoformat(timespec='seconds')
