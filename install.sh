#!/usr/bin/env bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 - "$bundle_dir" "$@" <<'PY'
import argparse,os,pathlib,shutil,time
p=argparse.ArgumentParser(description='Install Usage Tools for Codex for the current user; never changes watch-codex-quota.')
p.add_argument('source');p.add_argument('--prefix',default=str(pathlib.Path.home()/'.local'))
a=p.parse_args();source=pathlib.Path(a.source);prefix=pathlib.Path(a.prefix).expanduser().resolve()
dest=prefix/'lib/codex-limit-tools';bin_dir=prefix/'bin';suffix=time.strftime('%Y%m%d-%H%M%S')
if dest.exists():
    raise SystemExit(f'{dest} already exists. Stop its tracking daemon and move the old installation aside before reinstalling. Data is stored separately.')
dest.parent.mkdir(parents=True,exist_ok=True);bin_dir.mkdir(parents=True,exist_ok=True)
shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('codex-limit-estimator','codex-usage','codex-quota'):
    link=bin_dir/name
    if link.exists() or link.is_symlink():
        backup=bin_dir/(name+'.backup-'+suffix)
        if backup.exists():raise SystemExit('Backup name already exists: '+str(backup))
        link.rename(backup);print('Preserved previous command: '+str(backup))
    (dest/name).chmod(0o755);link.symlink_to(dest/name)
config=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',str(pathlib.Path.home()/'.config')))/'codex-limit-tools'
config.mkdir(parents=True,exist_ok=True)
if not (config/'prices.json').exists():shutil.copy2(dest/'prices.json',config/'prices.json')
print('Installed commands in '+str(bin_dir))
print('Editable prices: '+str(config/'prices.json'))
print('Existing watch-codex-quota and its state were not modified.')
PY
