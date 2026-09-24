# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""OS-bound fixture helpers; no real account or installation access."""
import json
import os
import pathlib
import subprocess


def symlink(test, link, target, **kwargs):
    try:
        link.symlink_to(target, **kwargs)
    except OSError as exc:
        if os.name == 'nt' and exc.winerror == 1314:
            test.skipTest('This Windows account lacks symlink privilege')
        raise


def assert_private(test, path):
    if os.name != 'nt':
        test.assertEqual(path.stat().st_mode & 0o777, 0o600)
        return
    # Inspect the actual ACL through an independent Windows API consumer.
    shell = pathlib.Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = """$ErrorActionPreference = 'Stop'
$acl = Get-Acl -LiteralPath $env:ACL_TEST_PATH
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($user, 'S-1-5-18', 'S-1-5-32-544')
$bad = @($acl.Access | Where-Object {
    $_.AccessControlType -eq 'Allow' -and
    $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -notin $allowed
})
@{ protected=$acl.AreAccessRulesProtected; bad=$bad.Count; count=$acl.Access.Count } | ConvertTo-Json -Compress
"""
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command', script],
                            env={**os.environ, 'ACL_TEST_PATH':str(path), 'PSModulePath':str(shell.parent/'Modules')}, capture_output=True,
                            text=True, timeout=15, check=True)
    acl = json.loads(result.stdout)
    test.assertEqual(acl['bad'], 0, 'ACL grants access to an ordinary other principal')
    test.assertGreater(acl['count'], 0)
