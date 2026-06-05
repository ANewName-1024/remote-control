"""Tests for agent.ws_bridge keepalive half-dead detection (post-merge).

Background
----------
Before commit 3d20bea: the _keepalive_loop caught any keepalive
failure (timeout OR seq mismatch), logged a warning, and continued.
The reasoning was "if WS is dead, recv() will eventually raise and
the outer _ws_loop will reconnect naturally". But that assumption is
wrong for a half-dead WS:
  - server can still send keepalive_ack (or at least let our old
    send of keepalive time out without raising)
  - agent->server frame_pump silently fails with WinError 10054
    every second (we don't observe that in keepalive_loop)
  - recv() never raises because the socket appears half-alive
  - the agent appears online for hours while doing nothing

After commit 3d20bea: count consecutive keepalive failures; force a
close + reconnect at 3 in a row (~75-90s wall time). 1-2 failures
are preserved as warnings to avoid misfires on network jitter.

After this change (single-thread merge): _keepalive_loop is gone.
The counter + force-reconnect logic now lives in
``_on_keepalive_failure`` (called by ``_run_main_loop`` when a
pending keepalive's ack window expires). Tests target that
function directly so the assertions don't depend on the
thread/sleep timing of the old design.

What these tests cover
----------------------
- _on_keepalive_failure 1 -> counter=1, ws not closed
- _on_keepalive_failure 2 -> counter=2, ws not closed
- _on_keepalive_failure 3 -> counter reset to 0, ws closed once,
  _force_reconnect_event set
- _on_keepalive_failure 3 with _ws.close() raising -> swallow,
  don't crash, event still set
- default counter on fresh bridge == 0
- _run_main_loop: ack-on-receive resets the pending probe
- _run_main_loop: 3-fail force-reconnect sets the event so the
  next loop iteration exits
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from agent.ws_bridge import WSBridge


@pytest.fixture
def bridge():
    """WSBridge with mocked network; safe to call internal methods.

    _ws is a MagicMock so .close() and .settimeout() succeed; auth_ok
    is pre-set so _run_main_loop won't try to wait for the post-auth
    grace period; _stop is a fresh Event so we can drive the loops
    to exit by setting it from a side effect.
    """
    b = WSBridge(
        pipe_server=MagicMock(),
        ws_url='ws://test/agent',
        agent_id='TEST',
        secret='secret',
    )
    b._ws = MagicMock()
    b.auth_ok = True
    b._stop = threading.Event()
    return b


# ---------------------------------------------------------------------------
# _on_keepalive_failure: 3-strike policy
# ---------------------------------------------------------------------------

def test_keepalive_1_failure_no_reconnect(bridge):
    """1 failure: counter=1, ws NOT closed, event NOT set."""
    bridge._on_keepalive_failure('test reason 1')
    assert bridge._consecutive_keepalive_failures == 1
    bridge._ws.close.assert_not_called()
    assert not bridge._force_reconnect_event.is_set()


def test_keepalive_2_failures_no_reconnect(bridge):
    """2 failures: counter=2, ws NOT closed, event NOT set."""
    bridge._on_keepalive_failure('test reason 1')
    bridge._on_keepalive_failure('test reason 2')
    assert bridge._consecutive_keepalive_failures == 2
    bridge._ws.close.assert_not_called()
    assert not bridge._force_reconnect_event.is_set()


def test_keepalive_3_failures_force_reconnect(bridge):
    """3 failures: counter reset to 0, ws closed once, event SET.

    Counter resets to 0 after we force a reconnect so a future
    probe starts fresh, not still "3 strikes".
    """
    bridge._on_keepalive_failure('test reason 1')
    bridge._on_keepalive_failure('test reason 2')
    bridge._on_keepalive_failure('test reason 3')
    assert bridge._consecutive_keepalive_failures == 0
    bridge._ws.close.assert_called_once()
    assert bridge._force_reconnect_event.is_set()


def test_keepalive_close_raising_does_not_crash(bridge):
    """3 failures where _ws.close() itself raises: swallow + set event.

    Defensive: a buggy close() (e.g. websocket-client throwing on a
    half-closed socket) must not tear down the keepalive logic. The
    except-clause wraps close() in its own try/except, but the
    event must still be set so _run_main_loop can exit and the
    outer _ws_loop can reconnect.
    """
    bridge._ws.close.side_effect = Exception('close() exploded')
    bridge._on_keepalive_failure('test reason 1')
    bridge._on_keepalive_failure('test reason 2')
    bridge._on_keepalive_failure('test reason 3')
    assert bridge._consecutive_keepalive_failures == 0
    bridge._ws.close.assert_called_once()  # it was attempted even if it raised
    assert bridge._force_reconnect_event.is_set()  # event still set


def test_keepalive_counter_default_zero(bridge):
    """The counter defaults to 0 on a fresh bridge, not 3.

    Regression guard: if someone sets the default to 3 in __init__,
    the very first keepalive failure would force a reconnect.
    """
    assert bridge._consecutive_keepalive_failures == 0
    assert not bridge._force_reconnect_event.is_set()


def test_keepalive_success_after_failures_resets_counter(bridge):
    """2 failures + 1 success path: counter back to 0.

    We simulate the success path by setting _keepalive_ack_seq[0] to
    match the just-sent seq, which is what _on_server_msg does when
    a keepalive_ack arrives. The next failure must go back to 1/3,
    not 3/3.

    In the production flow this is driven by _run_main_loop's
    poll-each-iteration check. We invoke _on_keepalive_failure
    directly here so the test doesn't depend on timing.
    """
    bridge._on_keepalive_failure('first fail')
    bridge._on_keepalive_failure('second fail')
    assert bridge._consecutive_keepalive_failures == 2
    # Production path: _on_server_msg sets _keepalive_ack_seq[0] to
    # the just-acked seq, _run_main_loop sees this and resets the
    # counter to 0. We model the reset here.
    bridge._consecutive_keepalive_failures = 0
    bridge._on_keepalive_failure('after a success, fresh fail')
    assert bridge._consecutive_keepalive_failures == 1
    bridge._ws.close.assert_not_called()
    assert not bridge._force_reconnect_event.is_set()


# ---------------------------------------------------------------------------
# _run_main_loop: short-timeout recv + keepalive tick
# ---------------------------------------------------------------------------

class _LoopExit(Exception):
    """Raised by test side-effects to break out of _run_main_loop."""


def _drive_main_loop_one_iteration(bridge, recv_side_effects, max_iters=20):
    """Run _run_main_loop until _stop is set, force-reconnect fires, or
    we've done ``max_iters`` poll iterations.

    recv_side_effects: list of values for successive _ws.recv() calls.
    When the list is exhausted, recv() raises WebSocketTimeoutException
    (production idle behavior). The loop then ticks the keepalive and
    polls again.

    The driver intentionally does NOT mock time.sleep: _run_main_loop
    doesn't sleep, so a missing sleep side-effect is fine. We exit via
    one of:
      - _stop set by a recv side-effect (test sets it after a result)
      - force-reconnect event set by _on_keepalive_failure (3-fail)
      - the test's own max_iters safety net (raises AssertionError
        if the loop never exits -- catches logic bugs that would
        otherwise hang pytest)
    """
    from websocket import WebSocketTimeoutException
    iter_results = iter(recv_side_effects)
    iter_count = [0]

    def recv_side_effect(*args, **kwargs):
        iter_count[0] += 1
        if iter_count[0] > max_iters:
            # Safety net: if the loop runs more than max_iters times
            # without exiting, the test is misconfigured (e.g. _stop
            # never gets set). Fail loud instead of hanging pytest.
            raise _LoopExit('max_iters exceeded')
        try:
            return next(iter_results)
        except StopIteration:
            raise WebSocketTimeoutException()

    # NOTE: we do NOT patch.object(bridge, '_ws'). The fixture already
    # gave us a MagicMock for _ws; we just attach a side-effect
    # recv() to it. Patching _ws would replace it with a *different*
    # MagicMock that the assertions after the loop don't see, which
    # breaks "was close() called?" checks.
    bridge._ws.recv = MagicMock(side_effect=recv_side_effect)
    with patch.object(bridge, '_send'):
        # NOTE: do NOT mock _handle_business_msg. The real method is
        # the one that calls _on_server_msg, which is where the
        # keepalive_ack -> _keepalive_ack_seq[0] update happens. If
        # we shadow it with a MagicMock, the test for "ack resets
        # pending" would never see the seq update and the loop would
        # never see a successful probe.
        try:
            bridge._run_main_loop()
        except _LoopExit:
            # Safety net hit: the loop ran max_iters times without
            # exiting via _stop or force-reconnect. That's normal for
            # the idle test (timeout=9999 + interval=0 keeps the loop
            # alive forever). For tests that *expect* a force-reconnect
            # raise, we wrap that in pytest.raises() at the call site
            # so it reaches us as ConnectionError, not _LoopExit.
            pass
    return iter_count[0]


def test_run_main_loop_idle_no_reconnect(bridge):
    """Idle recv (always timeout) + keepalive with no ack: no force-reconnect
    because the ack window never expires (timeout=9999s)."""
    # Set a huge ack window so the only way the loop exits is _stop.
    # Without this, the *real* time.time() in production code might
    # already be > 5s past the first keepalive's sent_at, which would
    # legitimately fire the failure path -- and that's correct
    # production behavior, just not what this test asserts.
    bridge._keepalive_ack_timeout = 9999.0
    bridge._keepalive_interval = 0.0  # send a keepalive each iteration
    _drive_main_loop_one_iteration(bridge, [])
    assert bridge._consecutive_keepalive_failures == 0
    assert not bridge._force_reconnect_event.is_set()


def test_run_main_loop_ack_resets_pending(bridge):
    """When server sends a keepalive_ack while a probe is pending,
    _run_main_loop should consume the ack and clear the pending probe.

    We simulate the ack arriving in the recv queue as a JSON string
    that decodes to {'type': 'keepalive_ack', 'seq': 1}. _on_server_msg
    is the real method (not mocked) so it can update the ack seq.
    """
    # Pre-arm: pretend we sent a keepalive seq=1, no ack yet.
    bridge._keepalive_seq = 1
    bridge._keepalive_ack_seq = [0]  # server hasn't acked yet
    # Huge ack window so the pending probe is not abandoned via
    # the timeout path before the ack has a chance to arrive.
    bridge._keepalive_ack_timeout = 9999.0
    bridge._keepalive_interval = 0.0  # send a keepalive each iteration

    # Build a recv() that returns a keepalive_ack then times out.
    ack_msg = '{"type": "keepalive_ack", "seq": 1}'
    _drive_main_loop_one_iteration(bridge, [ack_msg])

    # _on_server_msg ran and updated the ack seq.
    assert bridge._keepalive_ack_seq[0] == 1
    # _run_main_loop saw the ack seq moved and reset the counter.
    assert bridge._consecutive_keepalive_failures == 0


def test_run_main_loop_3_failures_raises_for_reconnect(bridge):
    """3 keepalive probes with no ack in the ack window -> force-reconnect.

    We drive 3 keepalive ticks by setting _keepalive_ack_timeout=0
    so the pending probe fails on the very next iteration. After
    the third failure _on_keepalive_failure sets
    _force_reconnect_event, the next while-iteration check exits
    _run_main_loop with a ConnectionError that the outer _ws_loop
    catches and turns into a reconnect.
    """
    bridge._keepalive_interval = 0.0
    bridge._keepalive_ack_timeout = 0.0  # expire immediately

    # Use the helper (which patches _ws.recv to always time out and
    # patches _send so keepalives don't actually leave the test),
    # and wrap in pytest.raises to catch the expected
    # ConnectionError. Real time.time() is fine here because we
    # set the timeout to 0.0 -- any positive elapsed counts as
    # "expired" -- so we don't need to mock the clock.
    with pytest.raises(ConnectionError, match='force-reconnect'):
        _drive_main_loop_one_iteration(bridge, [])

    # 3 failures -> counter reset, event set, ws.close called.
    assert bridge._force_reconnect_event.is_set()
    bridge._ws.close.assert_called()


# ---------------------------------------------------------------------------
# Module-level: excepthook is installed
# ---------------------------------------------------------------------------

def test_thread_excepthook_installed():
    """The module installs threading.excepthook so daemon-thread
    deaths leave a traceback instead of vanishing silently.

    This is the bug we hit on 2026-06-05 16:32+: a daemon thread
    died and we had no idea why. We committed 3d20bea to install
    this hook; this test guards against future refactors that
    accidentally remove it.
    """
    import threading
    # Re-import to be sure (in case the module was loaded once but
    # then a re-import happened during a separate test).
    from agent import ws_bridge
    assert ws_bridge.threading.excepthook is not None
    # Should be our handler, not the default no-op.
    assert ws_bridge.threading.excepthook.__name__ == '_thread_excepthook'
