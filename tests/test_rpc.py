# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Usage Tools for Codex contributors
"""Protocol failures using a synthetic stdio server; no network or model work."""
import json
import os
import sys
import threading
import time
import pathlib
import tempfile
import unittest

from codex_limit_tools.quota import RPC, MonitorError, QuotaSource

SERVER = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
assert sys.argv[1:] == ([] if os.name == 'nt' else ['app-server'])
mode = pathlib.Path(__file__ + '.mode').read_text()
for line in sys.stdin:
    message = json.loads(line)
    with pathlib.Path(__file__ + '.calls').open('a') as stream:
        stream.write(json.dumps(message) + '\\n')
    method = message.get('method')
    if method is None:
        assert message['error']['code'] == -32601
        continue
    assert method in ('initialize', 'initialized', 'account/read', 'account/rateLimits/read')
    if method == 'initialized': continue
    if mode == 'partial':
        sys.stdout.write('{'); sys.stdout.flush(); time.sleep(30)
    if mode == 'timeout': time.sleep(30)
    if mode == 'noise':
        print('not json', flush=True)
        print(json.dumps({'id':-123, 'result':'wrong'}), flush=True)
        print(json.dumps({'method':'notification'}), flush=True)
    if mode == 'oversized':
        sys.stdout.write('x' * (2 * 1024 * 1024 + 65536)); sys.stdout.flush(); continue
    if mode == 'closed': break
    if method == 'initialize':
        print(json.dumps({'id':'synthetic-server-request', 'method':'approval/request'}), flush=True)
        result = {}
    elif method == 'account/read':
        assert message['params'] == {'refreshToken':False}
        result = {'account': {'type':'chatgpt', 'id':'synthetic', 'planType':'synthetic'}}
    else:
        result = {'rateLimits': {'limitId':'codex', 'primary':
                  {'usedPercent':20, 'windowDurationMins':10080, 'resetsAt':9999999999}}}
    print(json.dumps({'id':message['id'], 'result':result}), flush=True)
'''


class ReadOnlyRPC(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fake = pathlib.Path(self.temp.name)/('app-server' if os.name == 'nt' else 'fake-codex')
        self.executable = sys.executable if os.name == 'nt' else str(self.fake)
        if os.name == 'nt':
            previous = os.getcwd()
            os.chdir(self.temp.name)
            self.addCleanup(os.chdir, previous)
        self.fake.write_text(SERVER)
        self.fake.chmod(0o700)

    def mode(self, value):
        pathlib.Path(str(self.fake)+'.mode').write_text(value)

    def test_server_requests_are_rejected_and_only_account_reads_follow(self):
        self.mode('normal')
        source = QuotaSource(self.executable)
        try:
            self.assertEqual(source.read()['left'], 80)
        finally:
            source.close()
        calls = [json.loads(line) for line in pathlib.Path(str(self.fake)+'.calls').read_text().splitlines()]
        self.assertEqual([m['method'] for m in calls if 'method' in m],
                         ['initialize', 'initialized', 'account/read', 'account/rateLimits/read'])
        rejected = [m for m in calls if 'method' not in m]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]['error']['code'], -32601)

    def test_timeout_closes_owned_server(self):
        self.mode('timeout')
        rpc = RPC(self.executable, .1)
        try:
            with self.assertRaisesRegex(MonitorError, 'timeout'):rpc.initialize()
        finally:
            rpc.close()
        self.assertIsNotNone(rpc.p.poll())

    def test_oversized_and_closed_output_fail_without_workload_requests(self):
        for mode, error in (('oversized', 'Oversized'), ('closed', 'closed')):
            self.mode(mode)
            rpc = RPC(self.executable, 2)
            try:
                with self.assertRaisesRegex(MonitorError, error):rpc.initialize()
            finally:
                rpc.close()
            self.assertIsNotNone(rpc.p.poll())

    def test_partial_noise_and_repeated_cleanup(self):
        before = {t.ident for t in threading.enumerate()}
        for mode in ('partial', 'noise', 'normal', 'normal'):
            self.mode(mode)
            rpc = RPC(self.executable, .3 if mode == 'partial' else 3)
            try:
                if mode == 'partial':
                    with self.assertRaisesRegex(MonitorError, 'timeout'):rpc.initialize()
                else:
                    rpc.initialize()
            finally:
                rpc.close()
                rpc.close()
            self.assertIsNotNone(rpc.p.poll())
            self.assertFalse(rpc.reader and rpc.reader.is_alive())
        self.assertEqual({t.ident for t in threading.enumerate()}, before)

    @unittest.skipUnless(os.name == 'nt', 'Windows pipe queue and executable resolution')
    def test_full_queue_cleanup_and_unsupported_shim(self):
        self.mode('oversized')
        rpc = RPC(self.executable, 3)
        rpc.send({'id':1, 'method':'initialize'})
        deadline = time.monotonic()+3
        while not rpc.chunks.full() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(rpc.chunks.full())
        rpc.close()
        self.assertFalse(rpc.reader.is_alive())
        shim = pathlib.Path(self.temp.name)/'unsupported.cmd'
        shim.write_text('@exit /b 99')
        with self.assertRaisesRegex(MonitorError, '--codex-bin'):RPC(str(shim), 1)
