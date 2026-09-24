#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
# Offline Linux dependency doctor. Does not install software or access an account.

set -u

plain=0
case "${1:-}" in
    --no-color) plain=1; shift ;;
    --help|-h)
        printf 'Usage: bash doctor.sh [--no-color]\n'
        printf 'Exit codes: 0 ready; 1 required dependency missing; 2 interactive or quota dependency needs attention.\n'
        exit 0 ;;
esac
if (($#)); then
    printf 'Unknown argument: %s\nUsage: bash doctor.sh [--no-color]\n' "$1" >&2
    exit 1
fi

if [[ ! -t 1 || -n "${NO_COLOR:-}" || "${TERM:-}" == dumb ]]; then
    plain=1
fi

status() {
    local state=$1 label=$2 detail=${3:-} color='' reset=''
    if (( ! plain )); then
        case "$state" in
            OK|FOUND) color=$'\033[32m' ;;
            MISSING) color=$'\033[31m' ;;
            WARN) color=$'\033[33m' ;;
            INFO) color=$'\033[36m' ;;
        esac
        reset=$'\033[0m'
    fi
    printf '  %s[%-7s]%s %s\n' "$color" "$state" "$reset" "$label"
    if [[ -n "$detail" ]]; then
        printf '              %s\n' "$detail"
    fi
}

printf '\n  Usage Tools for Codex | Linux doctor\n'
printf '  -----------------------------------\n'
printf '  Offline checks - no installation or account access.\n\n'

missing=0
warnings=0
if [[ "$OSTYPE" != linux* ]]; then
    status MISSING 'Linux' 'This doctor is for native Linux.'
    missing=$((missing + 1))
else
    status OK 'Linux / Bash' "Bash ${BASH_VERSION}"
fi

if python_path=$(type -P python3); then
    # -I ignores Python environment and user site; -S skips site hooks; -B avoids bytecode.
    # SQLite is exercised in memory. No database or other probe file is created.
    if probe=$("$python_path" -I -S -B - <<'PY' 2>/dev/null
import sys

def available(name, check=None):
    try:
        module = __import__(name)
        if check:
            check(module)
        return '1'
    except Exception:
        return '0'

def check_sqlite(module):
    connection = module.connect(':memory:')
    try:
        connection.execute('SELECT 1').fetchone()
    finally:
        connection.close()

print('|'.join((sys.version.split()[0],
                '1' if sys.version_info >= (3, 10) else '0',
                available('sqlite3', check_sqlite), available('fcntl'),
                available('select'), available('curses'))))
PY
    ); then
        IFS='|' read -r python_version supported sqlite_ok fcntl_ok select_ok curses_ok <<< "$probe"
        if [[ "$supported" == 1 ]]; then
            status OK "Python $python_version" "$python_path (used by install.sh)"
        else
            status MISSING "Python $python_version" 'Python 3.10 or newer is required by this project.'
            missing=$((missing + 1))
        fi
        for module in sqlite3 fcntl select; do
            case "$module" in
                sqlite3) result=$sqlite_ok; detail='SQLite works in memory; included with this Python build.' ;;
                fcntl) result=$fcntl_ok; detail='POSIX file locking is available.' ;;
                select) result=$select_ok; detail='Quota pipe polling is available.' ;;
            esac
            if [[ "$result" == 1 ]]; then
                status OK "$module" "$detail"
            else
                status MISSING "$module" 'Required Python component is unavailable; use a complete Linux Python build.'
                missing=$((missing + 1))
            fi
        done
        if [[ "$curses_ok" == 1 ]]; then
            status OK 'curses / interactive TUI' 'Import succeeds; terminal rendering was not tested.'
        else
            status WARN 'curses / interactive TUI' 'Unavailable in this Python build. Headless commands can still work.'
            warnings=$((warnings + 1))
        fi
    else
        status MISSING 'Python 3.10+' "Could not probe $python_path; check this interpreter."
        status INFO 'Python modules' 'SQLite, POSIX modules and curses could not be checked.'
        missing=$((missing + 1))
    fi
else
    status MISSING 'Python 3.10+' 'python3 is not on PATH; install a complete Python build.'
    status INFO 'Python modules' 'SQLite, POSIX modules and curses could not be checked.'
    missing=$((missing + 1))
fi

if codex_path=$(type -P codex) && [[ -f "$codex_path" && -x "$codex_path" ]]; then
    status FOUND 'Codex CLI (presence only)' "$codex_path"
    status INFO 'Quota / tracking integration' 'Codex was not executed; authentication and live access were not tested.'
else
    status WARN 'Codex CLI' 'Not found on PATH. Required for quota and tracking; offline reports can still work.'
    warnings=$((warnings + 1))
fi

printf '\n'
if (( missing )); then
    status MISSING 'Required dependencies need attention' "Blocking checks: $missing; other checks needing attention: $warnings"
    result=1
elif (( warnings )); then
    status WARN 'Core dependencies are ready' "Feature-specific checks needing attention: $warnings"
    result=2
else
    status OK 'Dependencies found' 'Live integration and terminal rendering were not tested by this doctor.'
    result=0
fi
if (( result )); then
    printf '  Resolve reported issues before installation.\n'
fi
printf '  Next: bash install.sh\n'
exit "$result"
