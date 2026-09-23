import pathlib
import tempfile
import time
import unittest
from unittest.mock import patch

from codex_limit_tools.common import connect, daemon_lock, get, put
from codex_limit_tools.tracker import (request_checkpoint, wait_checkpoint, claim_checkpoint,
                                      checkpoint_record, reject_checkpoints)


class Checkpoints(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name)
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        put(self.db, 'daemon', dict(instance_id='synthetic-daemon', checkpoint_protocol=1))
        put(self.db, 'control', dict(paused=False, shutdown=False, retained='synthetic'))
        self.db.commit()

    def test_one_request_claim_and_controls_remain_independent(self):
        with daemon_lock(self.path):
            row = request_checkpoint(self.db, self.path)
            with self.assertRaisesRegex(ValueError, 'already pending'):
                request_checkpoint(self.db, self.path)
            self.assertEqual(get(self.db, 'control')['retained'], 'synthetic')
            self.assertEqual(claim_checkpoint(self.db, 'synthetic-daemon'), row['id'])
            self.assertIsNone(claim_checkpoint(self.db, 'synthetic-daemon'))
            self.assertEqual(checkpoint_record(self.db, row['id'])['status'], 'sampling')
            reject_checkpoints(self.db, 'synthetic stopped')
            with self.assertRaisesRegex(ValueError, 'synthetic stopped'):
                wait_checkpoint(self.db, self.path, row['id'], .1)

    def test_absent_paused_shutdown_and_old_protocol_refused(self):
        with self.assertRaisesRegex(ValueError, 'absent'):
            request_checkpoint(self.db, self.path)
        with daemon_lock(self.path):
            for controls in (dict(paused=True), dict(shutdown=True)):
                put(self.db, 'control', controls)
                self.db.commit()
                with self.assertRaises(ValueError):request_checkpoint(self.db, self.path)
                self.assertEqual(get(self.db, 'control'), controls)
            put(self.db, 'control', {})
            put(self.db, 'daemon', {})
            self.db.commit()
            with self.assertRaisesRegex(ValueError, 'does not support'):
                request_checkpoint(self.db, self.path)
        self.assertEqual(self.db.execute('SELECT count(*) FROM checkpoints').fetchone()[0], 0)

    def test_pause_after_request_expiry_and_restart_never_sample(self):
        with daemon_lock(self.path):
            row = request_checkpoint(self.db, self.path)
            put(self.db, 'control', dict(paused=True, shutdown=False))
            self.db.commit()
            self.assertIsNone(claim_checkpoint(self.db, 'synthetic-daemon'))
            self.assertEqual(checkpoint_record(self.db, row['id'])['status'], 'error')
            put(self.db, 'control', {})
            self.db.commit()
            row = request_checkpoint(self.db, self.path)
            self.assertIsNone(claim_checkpoint(self.db, 'different-daemon'))
            self.assertEqual(checkpoint_record(self.db, row['id'])['status'], 'error')
            row = request_checkpoint(self.db, self.path)
            with patch('codex_limit_tools.tracker.time.time', return_value=row['expires']+1):
                self.assertIsNone(claim_checkpoint(self.db, 'synthetic-daemon'))
            self.assertEqual(checkpoint_record(self.db, row['id'])['status'], 'error')

    def test_wait_is_bounded_and_unknown_request_fails(self):
        with daemon_lock(self.path):
            row = request_checkpoint(self.db, self.path, .05)
            started = time.monotonic()
            with self.assertRaises(TimeoutError):wait_checkpoint(self.db, self.path, row['id'], .05)
            self.assertLess(time.monotonic()-started, .5)
        with self.assertRaisesRegex(ValueError, 'Unknown checkpoint'):
            checkpoint_record(self.db, 'missing')
