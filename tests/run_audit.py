# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Run offline tests with isolated homes, network denial and optional syscall traces."""
import argparse
from collections import Counter
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def trace_summary(log, work):
    """Resolve strace file targets; retain detail locally and fail on coverage gaps."""
    pending, cwd = {}, {}
    calls, mutations, outside, unknown, network = Counter(), [], [], [], []
    simple = {'mkdir', 'mkdirat', 'rmdir', 'unlink', 'unlinkat', 'chmod', 'chown', 'lchown',
              'truncate', 'utime', 'utimes', 'utimensat', 'rename', 'renameat', 'renameat2',
              'symlink', 'symlinkat', 'link', 'linkat'}
    for line in log.read_text().splitlines():
        match = re.match(r'^(\d+)\s+(.*)$', line)
        if not match:continue
        pid, call = match.groups()
        if '<unfinished ...>' in call:
            pending[pid] = call.split('<unfinished ...>')[0]
            continue
        if call.startswith('<... '):
            if pid not in pending:
                unknown.append(line)
                continue
            call = pending.pop(pid) + call.split('resumed>', 1)[1].lstrip()
        match = re.match(r'(\w+)\(', call)
        if not match:continue
        name = match[1]
        calls[name] += 1
        if name in ('connect', 'bind', 'sendto', 'sendmsg'):
            network.append(call)
        quoted = list(re.finditer(r'"(?:[^"\\]|\\.)*"', call))
        paths = []
        if name in simple or name in ('open', 'openat', 'openat2') and re.search(r'O_WRONLY|O_RDWR|O_CREAT|O_TRUNC', call):
            for item in quoted:
                try:value = json.loads(item[0])
                except ValueError:
                    unknown.append(line)
                    continue
                path = pathlib.Path(value)
                if not path.is_absolute():
                    annotations = re.findall(r'<(/[^>]*)>', call[:item.start()])
                    path = pathlib.Path(annotations[-1] if annotations else cwd.get(pid, str(ROOT)))/path
                paths.append(pathlib.Path(os.path.abspath(path)))
            if name in ('symlink', 'symlinkat', 'link', 'linkat'):paths = paths[-1:]
            # Returned descriptors expose the actual target of a followed link.
            target = re.search(r' = \d+<(/[^<>]*)', call)
            if name.startswith('open') and target:paths = [pathlib.Path(target[1])]
            if not paths:unknown.append(line)
            for path in paths:
                mutations.append(str(path))
                if (not path.is_relative_to(work) and str(path) not in ('/dev/null', '/dev/ptmx', '/dev/tty')
                        and not path.is_relative_to('/dev/pts')):
                    outside.append(line)
        if name in ('getcwd', 'chdir') and quoted and ' = -1 ' not in call:
            path = pathlib.Path(json.loads(quoted[0][0]))
            cwd[pid] = str(path if path.is_absolute() else pathlib.Path(cwd.get(pid, str(ROOT)))/path)
        if name in ('clone', 'clone3', 'vfork', 'fork') and (child := re.search(r' = (\d+)$', call)):
            cwd[child[1]] = cwd.get(pid, str(ROOT))
    unknown.extend(pending.values())
    details = dict(calls=dict(calls), mutation_targets=sorted(set(mutations)),
                   outside_writes=outside, unresolved=unknown, network=network)
    (work/'trace-summary.json').write_text(json.dumps(details, indent=2)+'\n')
    return dict(file_mutation_calls=len(mutations), outside_write_attempts=len(outside),
                unresolved_trace_calls=len(unknown), internet_syscalls=sum('AF_INET' in s for s in network),
                local_socket_calls=sum('AF_UNIX' in s for s in network))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test*.py')
    parser.add_argument('--trace', action='store_true', help='Require strace; retain file/process/network traces locally')
    args = parser.parse_args()
    tracer = shutil.which('strace') if args.trace else None
    if args.trace and not tracer:
        parser.error('--trace requires strace')
    base = ROOT/'.runtime/audit'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = pathlib.Path(tempfile.mkdtemp(prefix='run-', dir=base))
    for name in ('home', 'config', 'state', 'cache', 'codex', 'tmp', 'guard', 'outside'):
        (work/name).mkdir(mode=0o700)
    # No inherited account, proxy or credential environment. All test tempdirs stay here.
    env = dict(PATH=os.pathsep.join((str(work/'guard'), str(pathlib.Path(sys.executable).parent), os.defpath)),
               HOME=str(work/'home'), XDG_CONFIG_HOME=str(work/'config'),
               XDG_STATE_HOME=str(work/'state'), XDG_CACHE_HOME=str(work/'cache'),
               CODEX_HOME=str(work/'codex'), TMPDIR=str(work/'tmp'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join((str(work/'guard'), str(ROOT))),
               LANG='C.UTF-8', TERM='xterm-256color', CODEX_AUDIT_ROOT=str(work))
    (work/'guard/codex').write_text('#!'+sys.executable+'\nraise SystemExit("Real Codex is disabled in audit tests")\n')
    (work/'guard/codex').chmod(0o700)
    (work/'guard/sitecustomize.py').write_text('''import pathlib, sys
def deny_network(event, args):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.sendto'):
        with (pathlib.Path(__file__).parent / 'network-denied.log').open('a') as stream:
            stream.write(event + '\\n')
        raise RuntimeError('Network is disabled in audit tests')
sys.addaudithook(deny_network)
''')
    sentinels = [work/'outside/sentinel', work/'home/sentinel', work/'codex/auth.json']
    for sentinel in sentinels:
        sentinel.write_text('synthetic sentinel; no credentials\n')
    def snapshots():
        return [(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode, p.stat().st_mtime_ns)
                for p in sentinels]
    before = snapshots()
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', args.pattern, '-v']
    if tracer:
        command = [tracer, '-f', '-qq', '-s', '256', '-yy', '-e', 'trace=%file,%process,%network',
                   '-o', str(work/'syscalls.log'), *command]
    with (work/'tests.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    lines = (work/'tests.log').read_text().splitlines()
    summary = [line for line in lines if re.match(r'^Ran \d+ tests? in ', line) or line == 'OK' or line.startswith('FAILED (')]
    count = next((int(line.split()[1]) for line in summary if line.startswith('Ran ')), 0)
    unchanged = snapshots() == before
    denied = (work/'guard/network-denied.log').exists()
    trace = trace_summary(work/'syscalls.log', work) if tracer else {}
    ok = (result.returncode == 0 and count > 0 and unchanged and not denied
          and not any(trace.get(k) for k in ('outside_write_attempts', 'unresolved_trace_calls', 'internet_syscalls')))
    aggregate = dict(tests=count, exit_code=result.returncode, sentinels_unchanged=unchanged,
                     network_denials=int(denied), traced=bool(tracer), passed=ok, **trace)
    (work/'summary.json').write_text(json.dumps(aggregate, indent=2)+'\n')
    print('\n'.join(summary))
    print(json.dumps(aggregate, sort_keys=True))
    print('Local artifacts: '+str(work.relative_to(ROOT)))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
