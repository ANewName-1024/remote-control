"""Unit tests for ws_bridge.keepalive_ack matching logic.

Regression coverage for the 2026-06-10 silent half-dead bug: the
server was not echoing the ``seq`` field in keepalive_ack, so the
agent's probe matcher silently read seq=0 and force-reconnected every
5s. We test the matching path directly via _on_server_msg so we don't
need a live WS server.

Run: cd agent && python -m pytest ../tests/test_ws_bridge_keepalive.py -v
or:  cd agent && python ../tests/test_ws_bridge_keepalive.py
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import MagicMock

# Make 'agent' importable when running from the tests/ dir
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# We test ws_bridge directly, but the module imports ``agent.protocol``
# and a few agent-level helpers that expect a running Windows
# environment (win32file). Stub them out before import.
sys.modules.setdefault('win32file', MagicMock())
sys.modules.setdefault('win32pipe', MagicMock())
sys.modules.setdefault('win32api', MagicMock())

from agent import ws_bridge  # noqa: E402


def _make_bridge():
    """Construct a WSBridge without starting threads, for unit tests."""
    pipes = MagicMock()
    pipes.send_cmd = MagicMock()
    pipes.drain_frames = MagicMock(return_value=[])
    pipes.threads = []
    pipes.running = False
    b = ws_bridge.WSBridge.__new__(ws_bridge.WSBridge)
    # Initialize just the fields the keepalive path touches.
    b._keepalive_ack_seq = [0]
    b._keepalive_ts_window = __import__('collections').deque(maxlen=64)
    b._rtt_samples_ms = __import__('collections').deque(maxlen=20)
    b._keepalive_ack = __import__('threading').Event()
    b._consecutive_keepalive_failures = 0
    b.auth_ok = True
    b.ws_state = 'authed'
    b.cmds_recv = 0
    b._msg_type_stats = {}
    b._last_input_seq = 0
    b._keepalive_seq = 0
    b._outgoing_drops = 0
    import queue as _q
    b._outgoing_q = _q.Queue(maxsize=512)
    b.pipes = pipes
    # Logger shim
    import logging
    b.log = logging.getLogger('test')
    return b


class KeepaliveSeqContract(unittest.TestCase):
    """Server echoes seq back: probe matcher advances the watermark."""

    def test_canonical_seq_match_advances_watermark(self):
        b = _make_bridge()
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 42, 'ts': time.time()})
        self.assertEqual(b._keepalive_ack_seq[0], 42)
        self.assertTrue(b._keepalive_ack.is_set())

    def test_seq_only_no_ts(self):
        b = _make_bridge()
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 7})
        self.assertEqual(b._keepalive_ack_seq[0], 7)

    def test_higher_seq_overrides(self):
        b = _make_bridge()
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 5})
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 10})
        self.assertEqual(b._keepalive_ack_seq[0], 10)

    def test_lower_seq_does_not_regress(self):
        b = _make_bridge()
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 10})
        # Out-of-order: a stale ack with a lower seq must not
        # regress the watermark, or _run_main_loop's next probe
        # would see seq < pending and incorrectly time out.
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 7})
        self.assertEqual(b._keepalive_ack_seq[0], 10)


class KeepaliveTsWindowFallback(unittest.TestCase):
    """Server omits seq: ts-window fallback must catch valid acks."""

    def test_ts_in_window_accepted(self):
        b = _make_bridge()
        now = time.time()
        b._keepalive_ts_window.append(now)
        # Server (old/buggy) sends only ts, no seq. Fallback should
        # match because ts is within ±2s of a sent probe.
        b._on_server_msg({'type': 'keepalive_ack', 'ts': now})
        self.assertGreater(b._keepalive_ack_seq[0], 0,
                           'ts-window fallback should have advanced the watermark')

    def test_ts_outside_window_ignored(self):
        b = _make_bridge()
        # Window is empty (no probes sent), so any ts is unmatched.
        b._on_server_msg({'type': 'keepalive_ack', 'ts': time.time() - 60})
        self.assertEqual(b._keepalive_ack_seq[0], 0,
                         'stale ts must not falsely claim a probe')

    def test_no_seq_no_ts_completely_ignored(self):
        b = _make_bridge()
        b._keepalive_ts_window.append(time.time())
        b._on_server_msg({'type': 'keepalive_ack'})  # empty ack
        self.assertEqual(b._keepalive_ack_seq[0], 0)

    def test_rtt_recorded_when_ts_present(self):
        b = _make_bridge()
        sent_ts = time.time() - 0.05  # 50ms ago, simulating RTT
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 1, 'ts': sent_ts})
        # Should have recorded something close to 50ms
        self.assertEqual(len(b._rtt_samples_ms), 1)
        rtt = b._rtt_samples_ms[0]
        self.assertGreater(rtt, 30)
        self.assertLess(rtt, 200)


class KeepaliveMalformed(unittest.TestCase):
    """Defensive: junk ack messages don't crash anything."""

    def test_string_seq_is_ignored(self):
        b = _make_bridge()
        b._on_server_msg({'type': 'keepalive_ack', 'seq': 'not-a-number'})
        # Bad types should be ignored, not crash the matcher.
        self.assertEqual(b._keepalive_ack_seq[0], 0)

    def test_negative_ts_in_window(self):
        b = _make_bridge()
        b._keepalive_ts_window.append(time.time())
        b._on_server_msg({'type': 'keepalive_ack', 'ts': -1.0})
        # -1.0 is nowhere near our window, so must be ignored.
        self.assertEqual(b._keepalive_ack_seq[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)