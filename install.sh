#!/usr/bin/env bash
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 - "$bundle_dir" "$@" <<'PY'
import pathlib,sys
source=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(source))
from codex_limit_tools.installer import main
main(sys.argv[2:],source=source)
PY
