"""Local installation and reversible upgrades; never start a collector."""
import argparse
from contextlib import ExitStack, closing
import fcntl
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

from .common import SCHEMA_VERSION, daemon_lock, data_path

COMMANDS = ('codex-limit-estimator', 'codex-usage', 'codex-quota')
MODULES = ('__init__', 'cli', 'common', 'estimate', 'installer', 'quota', 'render', 'tracker', 'tui', 'usage')
PAYLOAD = (*COMMANDS, 'install.sh', 'prices.json', 'README.md',
           *(f'codex_limit_tools/{name}.py' for name in MODULES))
OPTIONAL_PAYLOAD = ('TUI-preview.png', 'docs/ANALYSIS.md', 'docs/UPGRADING.md', 'docs/COMMANDS.md')


def copy_payload(source, stage):
    # An explicit distribution manifest excludes checkout metadata and local state.
    for name in (*PAYLOAD, *(n for n in OPTIONAL_PAYLOAD if (source/n).is_file())):
        item = source/name
        if not item.is_file() or item.is_symlink():
            raise ValueError('Missing or non-regular distribution file: '+name)
        target = stage/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
    for name in COMMANDS:
        (stage/name).chmod(0o755)


def validate_payload(stage):
    from .usage import load_prices
    load_prices(stage/'prices.json')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'}
    for name in COMMANDS:
        result = subprocess.run([sys.executable, str(stage/name), '--help'],
                                capture_output=True, text=True, env=env, timeout=15)
        if result.returncode:
            raise ValueError('Staged command validation failed: '+name)


def backup_database(path, suffix):
    database = path/'tracking.sqlite3'
    if not database.exists():
        return None
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)) as source:
        version = source.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError(f'Database schema {version} is newer than this package supports')
        backup = path/('tracking.sqlite3.backup-upgrade-'+suffix)
        with closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        backup.chmod(0o600)
    return backup


def install(source, prefix, state_dirs, config_dir, upgrade=False):
    source, prefix = source.resolve(), prefix.expanduser().resolve()
    config_dir = config_dir.expanduser().resolve()
    state_dirs = sorted({data_path(p) for p in state_dirs})
    dest, bin_dir = prefix/'lib/codex-limit-tools', prefix/'bin'
    if dest.is_symlink() or dest.exists() and not dest.is_dir():
        raise ValueError('Installation path must be a regular directory')
    if dest.exists() and not upgrade:
        raise ValueError('Installation already exists. Shutdown its daemon, then use --upgrade (or --update).')
    if any(p == dest or dest in p.parents for p in [config_dir, *state_dirs]):
        raise ValueError('Configuration and tracking data must be outside the installation directory')
    for name in PAYLOAD:
        if not (source/name).is_file() or (source/name).is_symlink():
            raise ValueError('Missing or non-regular distribution file: '+name)
    suffix = time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    dest.parent.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    stage = dest.with_name(dest.name+'.stage-'+suffix)
    previous = dest.with_name(dest.name+'.backup-'+suffix)
    failed = dest.with_name(dest.name+'.failed-'+suffix)
    with ExitStack() as stack:
        lock = stack.enter_context((dest.parent/'.codex-limit-tools.install.lock').open('a'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another installation is in progress') from None
        # Recheck after the installation lock in case another process just finished.
        if dest.exists() and not upgrade:
            raise ValueError('Installation already exists; use --upgrade after shutdown')
        for path in state_dirs:
            stack.enter_context(daemon_lock(path))
        for name in COMMANDS:
            if (bin_dir/name).is_dir() and not (bin_dir/name).is_symlink():
                raise ValueError('Command path is a directory: '+name)
        stage.mkdir(mode=0o755)
        copy_payload(source, stage)
        validate_payload(stage)
        backups = [p for path in state_dirs if (p := backup_database(path, suffix))]
        command_backups = {}
        for name in COMMANDS:
            link = bin_dir/name
            if link.exists() or link.is_symlink():
                backup = bin_dir/(name+'.backup-'+suffix)
                if link.is_symlink():
                    backup.symlink_to(os.readlink(link))
                else:
                    shutil.copy2(link, backup)
                command_backups[name] = backup
        moved_previous = False
        installed = False
        switched = []
        try:
            if dest.exists():
                dest.rename(previous)
                moved_previous = True
            stage.rename(dest)
            installed = True
            for name in COMMANDS:
                temporary = bin_dir/(name+'.stage-'+suffix)
                temporary.symlink_to(dest/name)
                os.replace(temporary, bin_dir/name)
                switched.append(name)
            config_dir.mkdir(parents=True, exist_ok=True)
            try:
                with (config_dir/'prices.json').open('x') as stream:
                    stream.write((dest/'prices.json').read_text())
            except FileExistsError:
                pass
        except BaseException:
            for name in reversed(switched):
                if name in command_backups:
                    os.replace(command_backups[name], bin_dir/name)
                else:
                    (bin_dir/name).unlink()
            if installed:
                dest.rename(failed)
            if moved_previous:
                previous.rename(dest)
            raise
    return dict(destination=dest, previous=previous if moved_previous else None,
                database_backups=backups, command_backups=list(command_backups.values()))


def main(argv=None, *, source=None):
    parser = argparse.ArgumentParser(description='Install or safely update Usage Tools for Codex without starting collection.')
    parser.add_argument('--prefix', default=str(pathlib.Path.home()/'.local'))
    parser.add_argument('--upgrade', '--update', action='store_true', help='Preserve and replace an existing installation after daemon shutdown')
    parser.add_argument('--data-dir', action='append', help='Tracking directory to lock and back up; repeat for every configured collector')
    args = parser.parse_args(argv)
    config = pathlib.Path(os.environ.get('XDG_CONFIG_HOME', str(pathlib.Path.home()/'.config')))/'codex-limit-tools'
    paths = args.data_dir or [data_path()]
    try:
        result = install(source or pathlib.Path(__file__).resolve().parent.parent, pathlib.Path(args.prefix), paths, config, args.upgrade)
    except (OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f'Installation failed: {exc}\nExisting backups and any staging files are retained.\n')
    print('Installed commands in '+str(pathlib.Path(args.prefix).expanduser()/'bin'))
    if result['previous']:
        print('Preserved previous installation: '+str(result['previous']))
    for backup in result['database_backups']:
        print('SQLite backup: '+str(backup))
    for backup in result['command_backups']:
        print('Preserved command: '+str(backup))
    print('External prices preserved at '+str(config/'prices.json'))
    print('No collector was started and no database was migrated. Next: migrate, verify history, then resume.')
    print('Use the same --data-dir for those commands. The separate quota watcher is unchanged.')
