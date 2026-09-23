import hashlib,json,os,pathlib,sqlite3,time

def data_path(value=None):
    return pathlib.Path(value or os.path.join(os.environ.get('XDG_STATE_HOME',str(pathlib.Path.home()/'.local/state')),'codex-limit-estimator')).expanduser().resolve()

def connect(path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(path/'tracking.sqlite3',timeout=30)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=30000')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,identity TEXT,offset INTEGER,thread TEXT,mtime INTEGER);
    CREATE TABLE IF NOT EXISTS turns(thread TEXT,turn TEXT,model TEXT,PRIMARY KEY(thread,turn,model));
    CREATE TABLE IF NOT EXISTS responses(id TEXT PRIMARY KEY,thread TEXT,turn TEXT,ts REAL,inp INTEGER,cached INTEGER,writes INTEGER,out INTEGER,reason INTEGER,direct_model TEXT);
    CREATE INDEX IF NOT EXISTS response_ts ON responses(ts);
    CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY,started REAL,reason TEXT,label TEXT,price_hash TEXT,config TEXT);
    CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,segment INTEGER,ts REAL,used REAL,reset_at REAL,metrics TEXT);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,detail TEXT);
    ''')
    return db

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
