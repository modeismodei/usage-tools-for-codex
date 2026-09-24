# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_limit_tools.common import connect, daemon_lock, private_open, atomic_text
from codex_limit_tools.tracker import running
from native_support import assert_private

ROOT = pathlib.Path(__file__).resolve().parents[1]


class NativeFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name)/'state'

    def test_empty_lock_probe_and_process_contention(self):
        self.assertFalse(running(self.path))
        self.assertFalse(self.path.exists())
        with daemon_lock(self.path) as lock:
            self.assertFalse(os.get_inheritable(lock.fileno()))
            self.assertEqual((self.path/'daemon.lock').stat().st_size, 0)
            self.assertTrue(running(self.path))
            with self.assertRaisesRegex(ValueError, 'active'):
                with daemon_lock(self.path):pass
            code = "from pathlib import Path; from codex_limit_tools.common import daemon_lock; import sys; "
            code += "\ntry:\n with daemon_lock(Path(sys.argv[1])):pass\nexcept ValueError:sys.exit(17)"
            child = subprocess.run([sys.executable, '-B', '-c', code, str(self.path)], cwd=ROOT,
                                   capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 17, child.stderr)
        self.assertFalse(running(self.path))
        with daemon_lock(self.path):pass
        before=(self.path/'daemon.lock').stat().st_mtime_ns
        for _ in range(3):self.assertFalse(running(self.path))
        self.assertEqual((self.path/'daemon.lock').stat().st_mtime_ns,before)
        with patch('codex_limit_tools.tracker.lock_file', side_effect=PermissionError('synthetic')):
            with self.assertRaises(PermissionError):running(self.path)

    def test_owner_exit_releases_lock(self):
        child = subprocess.Popen([sys.executable, '-B', '-c',
            "from pathlib import Path; from codex_limit_tools.common import daemon_lock; import sys; "
            "\nwith daemon_lock(Path(sys.argv[1])):\n print(1,flush=True)\n sys.stdin.readline()",
            str(self.path)], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline().strip(), b'1')
            self.assertTrue(running(self.path))
            child.communicate(b'\n', timeout=10)
            self.assertEqual(child.returncode,0)
        finally:
            if child.poll() is None:child.kill();child.communicate()
        with daemon_lock(self.path):pass

    def test_private_sidecars_append_exclusive_and_atomic_failure(self):
        db=connect(self.path)
        try:
            for file in self.path.glob('tracking.sqlite3*'):assert_private(self,file)
            log=self.path/'log'
            with private_open(log) as stream:stream.write(b'first')
            with private_open(log) as stream:stream.write(b'second')
            self.assertEqual(log.read_bytes(),b'firstsecond')
            with self.assertRaises(FileExistsError):private_open(log,'xb')
            before=log.read_bytes()
            with self.assertRaises(RuntimeError):
                with atomic_text(log) as stream:
                    stream.write('partial')
                    raise RuntimeError('synthetic')
            self.assertEqual(log.read_bytes(),before)
            with self.assertRaises(FileExistsError):
                with atomic_text(log,replace=False) as stream:stream.write('new')
            self.assertEqual(log.read_bytes(),before)
            assert_private(self,log)
        finally:db.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows opened-handle and reparse validation')
    def test_native_alias_validation_before_any_write(self):
        from codex_limit_tools import installer
        sentinel=pathlib.Path(self.temp.name)/'sentinel'
        sentinel.write_bytes(b'synthetic unchanged')
        alias=pathlib.Path(self.temp.name)/'hardlink'
        os.link(sentinel,alias)
        with patch('codex_limit_tools.common.regular_private_path'):
            with self.assertRaises(ValueError):
                with private_open(alias) as stream:stream.write(b'changed')
        self.assertEqual(sentinel.read_bytes(),b'synthetic unchanged')
        prefix=pathlib.Path(self.temp.name)/'prefix'
        prefix.mkdir()
        target=pathlib.Path(self.temp.name)/'outside'
        target.mkdir()
        junction=prefix/'lib'
        made=subprocess.run([os.environ['COMSPEC'],'/d','/c','mklink','/J',str(junction),str(target)],
                            capture_output=True,timeout=10)
        self.assertEqual(made.returncode,0,made.stderr)
        try:
            with self.assertRaisesRegex(ValueError,'directory'):
                installer.install(ROOT,prefix,[self.path],prefix/'config')
            self.assertEqual(list(target.iterdir()),[])
        finally:
            junction.rmdir()

    @unittest.skipUnless(os.name == 'nt', 'Windows existing-directory ACL preservation')
    def test_existing_public_directory_is_refused_without_rewriting_acl(self):
        from codex_limit_tools import platform_io as native
        import ctypes as ct
        self.path.mkdir()
        descriptor=native.wt.LPVOID()
        native.checked(native.convert_sd('D:P(A;OICI;FA;;;WD)',1,ct.byref(descriptor),None))
        set_security=native.api(native.security,'SetFileSecurityW',native.wt.BOOL,
                                native.wt.LPCWSTR,native.wt.DWORD,native.wt.LPVOID)
        try:
            native.checked(set_security(str(self.path),0x80000004,descriptor))
        finally:native.local_free(descriptor)
        with self.assertRaisesRegex(ValueError,'private ACL'):connect(self.path)
        self.assertEqual(list(self.path.iterdir()),[])
        # Refusal leaves the existing broad ACL intact, including on a second attempt.
        with self.assertRaisesRegex(ValueError,'private ACL'):connect(self.path)
