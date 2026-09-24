# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Native Python entry for the existing installer engine."""
import pathlib
import sys

sys.dont_write_bytecode = True
from codex_limit_tools.installer import main

if __name__ == '__main__':
    main(source=pathlib.Path(__file__).resolve().parent)
