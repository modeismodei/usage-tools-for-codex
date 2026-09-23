# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Run offline tests, retain verbose local logs and print only the summary."""
import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test*.py', help='unittest discovery pattern')
    args = parser.parse_args()
    log_dir = ROOT/'logs'
    log_dir.mkdir(exist_ok=True)
    log = log_dir/('checks-'+re.sub(r'[^a-zA-Z0-9_-]', '_', args.pattern)+'.log')
    with log.open('w') as stream:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                                 '-p', args.pattern, '-v'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    lines = log.read_text().splitlines()
    count = 0
    for line in lines:
        if re.match(r'^Ran \d+ tests? in ', line) or line == 'OK' or line.startswith('FAILED ('):
            print(line)
        if re.match(r'^Ran \d+ tests? in ', line):
            count = int(line.split()[1])
    warnings = sum('Warning:' in line for line in lines)
    if warnings:
        print(f'Warnings in log: {warnings}')
    print(f'Exit code: {result.returncode}; detailed log: {log.relative_to(ROOT)}')
    return result.returncode or (1 if count == 0 else 0)


if __name__ == '__main__':
    sys.exit(main())
