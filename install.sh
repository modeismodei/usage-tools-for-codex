#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
set -euo pipefail
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 - "$bundle_dir" "$@" <<'PY'
import pathlib,sys
sys.dont_write_bytecode=True
source=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(source))
from codex_limit_tools.installer import main
main(sys.argv[2:],source=source)
PY
