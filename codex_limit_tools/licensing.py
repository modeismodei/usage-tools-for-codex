# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Shared license notices, without collection or configuration side effects."""
import argparse
import pathlib
import sys
from . import __version__

LICENSE_ID = 'GPL-3.0-only'
COPYRIGHT = 'Copyright (C) 2026 Usage Tools for Codex contributors'
SHORT_NOTICE = 'GNU GPLv3; no warranty. Free software: redistribution is permitted under GPLv3. See --license.'


def license_text():
    return (pathlib.Path(__file__).resolve().parent.parent/'LICENSE').read_text()


class LicenseAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(license_text(), end='')
        parser.exit()


def add_license_options(parser):
    parser.epilog = SHORT_NOTICE
    parser.add_argument('--license', action=LicenseAction, nargs=0,
                        help='Show the complete GPLv3 license and warranty terms, then exit')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__} (GPLv3)')


def startup_notice():
    print(f'Usage Tools for Codex {__version__} | {COPYRIGHT}\n{SHORT_NOTICE}', file=sys.stderr)
