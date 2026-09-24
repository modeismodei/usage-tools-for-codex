# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Read-only Codex app-server RPC, adapted from the quota v2 monitor."""
import hashlib,json,math,os,pathlib,queue,select,shutil,subprocess,threading,time
class MonitorError(Exception):
    pass

def resolve_executable(executable):
    if os.name != 'nt':
        return executable
    # Own a native process directly; npm/PowerShell shims can orphan children.
    value = os.fspath(executable)
    native = shutil.which(value + '.exe') if pathlib.Path(value).suffix == '' else None
    found = native or shutil.which(value)
    if not found or pathlib.Path(found).suffix.lower() != '.exe':
        raise MonitorError('Native Codex executable required; use --codex-bin with the full '
                           'path to codex.exe (including a desktop-app bundled executable). '
                           'Unresolved .cmd/.ps1 shims are not supported.')
    return found


class RPC:

    def __init__(self, executable, timeout):
        self.timeout = timeout
        self.seq = 0
        self.buf = b''
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        self.p = subprocess.Popen([resolve_executable(executable), 'app-server'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, **options)
        self.reader = None
        self.stopping = threading.Event()
        if os.name == 'nt':
            self.chunks = queue.Queue(maxsize=8)
            self.reader = threading.Thread(target=self._read_pipe, name='quota-pipe-reader', daemon=True)
            self.reader.start()

    def _read_pipe(self):
        while not self.stopping.is_set():
            try:
                chunk = os.read(self.p.stdout.fileno(), 65536)
            except OSError:
                chunk = b''
            while not self.stopping.is_set():
                try:
                    self.chunks.put(chunk, timeout=.05)
                    break
                except queue.Full:
                    continue
            if not chunk:
                return

    def close(self):
        self.stopping.set()
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()
        if self.reader is not None:
            self.reader.join(timeout=3)
            if self.reader.is_alive():
                raise MonitorError('Owned app-server pipe reader did not exit')
        self.p.stdin.close()
        self.p.stdout.close()

    def send(self, msg):
        if 'method' in msg and msg['method'] not in ('initialize', 'initialized', 'account/read', 'account/rateLimits/read'):
            raise MonitorError('RPC method not allowed')
        data = (json.dumps(msg) + '\n').encode()
        self.p.stdin.write(data)

    def call(self, method, params=None):
        if method not in ('initialize', 'account/read', 'account/rateLimits/read'):
            raise MonitorError('RPC method not allowed')
        self.seq += 1
        req = {'id': self.seq, 'method': method}
        if params is not None:
            req['params'] = params
        self.send(req)
        deadline = time.monotonic() + self.timeout
        while True:
            if time.monotonic() >= deadline:
                raise MonitorError('RPC timeout')
            if b'\n' not in self.buf:
                if self.reader is not None:
                    try:
                        chunk = self.chunks.get(timeout=max(0, deadline - time.monotonic()))
                    except queue.Empty:
                        raise MonitorError('RPC timeout') from None
                else:
                    ready, _, _ = select.select([self.p.stdout], [], [], max(0, deadline - time.monotonic()))
                    if not ready:
                        raise MonitorError('RPC timeout')
                    chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    raise MonitorError('app-server closed its output')
                self.buf += chunk
                if len(self.buf) > 2 * 1024 * 1024:
                    raise MonitorError('Oversized RPC output')
                continue
            line, self.buf = self.buf.split(b'\n', 1)
            try:
                msg = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(msg, dict):
                continue
            if 'method' in msg:
                if 'id' in msg:
                    self.send({'id': msg['id'], 'error': {'code': -32601, 'message': 'Read-only quota client does not handle server requests'}})
                continue
            if msg.get('id') != self.seq:
                continue
            if 'error' in msg:
                code = (msg['error'] or {}).get('code', 'unknown')
                raise MonitorError(f'RPC {method} failed (code {code}); check Codex login/version manually')
            return msg.get('result')

    def initialize(self):
        self.call('initialize', {'clientInfo': {'name': 'usage_tools_for_codex', 'version': '2.0.0'}})
        self.send({'method': 'initialized', 'params': {}})

def number(x):
    return isinstance(x, (int, float)) and (not isinstance(x, bool)) and math.isfinite(x)

class QuotaSource:
    def __init__(self, codex_bin='codex', bucket='codex', minutes=10080):
        self.rpc=None;self.executable=codex_bin;self.bucket=bucket;self.minutes=minutes
    def close(self):
        if self.rpc:self.rpc.close();self.rpc=None
    def read(self):
        try:
            if self.rpc is None:
                self.rpc=RPC(self.executable,20);self.rpc.initialize()
            account=self.rpc.call('account/read',{'refreshToken':False}).get('account')
            if not isinstance(account,dict) or account.get('type')!='chatgpt':
                raise MonitorError('A ChatGPT-authenticated Codex account is required')
            identity=account.get('email') or account.get('id')
            if not identity:raise MonitorError('Account identity unavailable; refusing to mix accounts')
            result=self.rpc.call('account/rateLimits/read')
            buckets=result.get('rateLimitsByLimitId')
            rate=buckets.get(self.bucket) if isinstance(buckets,dict) and buckets else result.get('rateLimits')
            if not isinstance(rate,dict) or rate.get('limitId') not in (None,self.bucket):raise MonitorError('Quota bucket unavailable')
            candidates=[rate.get(k) for k in ['primary','secondary']]
            wins=[w for w in candidates if isinstance(w,dict) and w.get('windowDurationMins')==self.minutes]
            if len(wins)!=1:raise MonitorError('Expected a single weekly quota window; refusing to guess')
            w=wins[0];used=w.get('usedPercent');reset=w.get('resetsAt')
            if not number(used) or not 0<=used<=100:raise MonitorError('Invalid usedPercent')
            if reset is not None and (not number(reset) or reset<=0):raise MonitorError('Invalid reset timestamp')
            return {'used':used,'left':100-used,'reset_at':reset,
                    'account':hashlib.sha256(str(identity).encode()).hexdigest(),
                    'plan':account.get('planType'),'bucket':self.bucket,'at':time.time()}
        except Exception:
            self.close();raise
