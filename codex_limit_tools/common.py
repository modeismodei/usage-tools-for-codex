# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
import hashlib,json,os,pathlib,sqlite3,stat,tempfile,time,uuid
from contextlib import closing,contextmanager

from .platform_io import WINDOWS, is_alias, private_mkdir, lock_file, unlock_file

SCHEMA_VERSION = 2


def regular_private_path(path):
    """Mutable state must not alias another file or follow a special file."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or is_alias(path):
        raise ValueError('State file must be regular and have one link: '+path.name)


def private_open(path, mode='ab'):
    """Create owner-only files, refusing symlinks and hard links before writing."""
    regular_private_path(path)
    if WINDOWS:
        from .platform_io import windows_open
        return windows_open(path, mode)
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    flags |= os.O_EXCL if mode in ('x', 'xb') else os.O_APPEND
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('State file must be regular and have one link: '+path.name)
        return os.fdopen(fd, mode)
    except BaseException:
        os.close(fd)
        raise


def validate_database_files(path):
    for suffix in ('', '-wal', '-shm', '-journal'):
        regular_private_path(path/('tracking.sqlite3'+suffix))


@contextmanager
def atomic_text(path, *, replace=True, newline=None):
    """Publish a complete owner-only file without following destination links."""
    if WINDOWS:
        temporary = path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
        stream = private_open(temporary, 'x')
    else:
        fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
        temporary = pathlib.Path(temporary)
        stream = os.fdopen(fd, 'w', encoding='utf-8', newline=newline)
    if WINDOWS:
        stream.reconfigure(encoding='utf-8', newline=newline)
    try:
        with stream:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Exclusive publication preserves even an existing dangling symlink.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

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
    private_mkdir(path)
    with private_open(path / 'daemon.lock') as lock:
        try:
            lock_file(lock)
        except BlockingIOError:
            raise ValueError('Collector is active. Run codex-limit-estimator shutdown '
                             'with the same --data-dir, wait for Daemon: offline, then retry.') from None
        try:
            yield lock
        finally:
            unlock_file(lock)


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
        with private_open(backup_path, 'xb'):pass
        with closing(sqlite3.connect(backup_path)) as backup:
            db.backup(backup)
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
    validate_database_files(path)
    if readonly:
        db=sqlite3.connect((path/'tracking.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    else:
        private_mkdir(path)
        with private_open(path/'tracking.sqlite3'):pass
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
