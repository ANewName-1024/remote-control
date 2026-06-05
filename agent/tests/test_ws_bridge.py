"""Tests for agent.ws_bridge keepalive half-dead detection.

Background
----------
Before this fix, the _keepalive_loop caught any keepalive failure
(timeout OR seq mismatch), logged a warning, and continued. The
reasoning was "if WS is dead, recv() will eventually raise and the
outer _ws_loop will reconnect naturally". But that assumption is
wrong for a half-dead WS:
  - server can still send keepalive_ack (or at least let our old
    send of keepalive time out without raising)
  - agent->server frame_pump silently fails with WinError 10054
    every second (we don't observe that in keepalive_loop)
  - recv() never raises because the socket appears half-alive
  - the agent appears online for hours while doing nothing

The new policy: count consecutive keepalive failures; force a close
+ reconnect at 3 in a row (~75-90s wall time). 1-2 failures are
preserved as warnings to avoid misfires on network jitter that would
also reset the App-side coordinate mapping.

What these tests cover
----------------------
- 1 failure  -> counter=1, ws not closed
- 2 failures -> counter=2, ws not closed
- 3 failures -> counter=0 (reset), ws closed exactly once
- 2 failures + 1 success -> counter reset to 0, ws not closed
- 3 failures with _ws.close() raising -> swallow, don't crash
"""
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.ws_bridge import WSBridge


@pytest.fixture
def bridge():
    """WSBridge with mocked network; safe to call internal methods.

    NOTE on _keepalive_ack: we use a SimpleNamespace instead of a
    real threading.Event. Setting `bridge._keepalive_ack.wait =
    MagicMock(...)` on a real Event instance in some test runners
    (specifically pytest's module-level mock discovery) does not
    shadow the bound method reliably -- pytest may have already
    rebound the descriptor before we get to the assignment.
    SimpleNamespace has no descriptor magic; the attribute is just
    a regular slot, so the mock is what gets called.
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
    # ack state: a `wait(timeout)` mock replaced per test, plus a
    # seq-mismatch list the production code reads/writes.
    b._keepalive_ack = SimpleNamespace(
        wait=MagicMock(return_value=False),
        # Production also calls .clear() and .set() on _keepalive_ack
        # (it expects a threading.Event). Stub them so the
        # exception path doesn't AttributeError out of the loop.
        clear=MagicMock(),
        set=MagicMock(),
    )
    b._keepalive_ack_seq = [0]
    return b


def _run_n_keepalive_cycles(bridge, n, wait_results):
    """Run _keepalive_loop for exactly n cycles.

    `wait_results` is a list of bools; each cycle consumes one
    (False = timeout, True = ack arrived). For True cycles we also
    update bridge._keepalive_ack_seq so the seq check passes.

    The complication: _keepalive_loop re-assigns
    `self._keepalive_ack = threading.Event()` at the top of its body
    (line 256). That clobbers any mock the fixture set. We patch
    `threading.Event` itself so the loop's "new Event()" call returns
    a SimpleNamespace we control. The side-effect function for
    `wait` is held in a single-element list so the helper can swap
    it BEFORE the loop starts (the loop will read it on the first
    probe).
    """
    assert len(wait_results) >= n

    # Mutable container for the current wait side-effect. The FakeEvent
    # closure below reads this on every probe, so we can wire the
    # actual side-effect function in once and let all n cycles consume
    # from the same iter.
    current_wait_fn = [lambda timeout: False]  # default: timeout

    class FakeEvent:
        def __init__(self):
            self.set = MagicMock()
            self.clear = MagicMock()
            # Use *args, **kwargs because the production code calls
            # `self._keepalive_ack.wait(timeout=5.0)` with a
            # keyword arg -- a `lambda t: ...` would not match
            # the parameter name and MagicMock would surface a
            # TypeError. The forwarder below unpacks whatever
            # MagicMock passes to the actual side-effect fn.
            self._wait_mock = MagicMock(
                side_effect=lambda *a, **kw: current_wait_fn[0](*a, **kw)
            )
        @property
        def wait(self):
            return self._wait_mock

    iter_results = iter(wait_results[:n])
    def wait_side_effect(*args, **kwargs):
        # Production calls `wait(timeout=5.0)`. We don't care about
        # the timeout value (it would block the test for 5s); we
        # just need to return whether the ack arrived.
        _ = (args, kwargs)
        ok = next(iter_results, False)
        if ok:
            # Update seq so the "ack seq >= sent seq" check passes
            bridge._keepalive_ack_seq[0] = bridge._keepalive_seq
        return ok

    cycles_done = [0]
    def sleep_side_effect(_):
        cycles_done[0] += 1
        if cycles_done[0] >= n:
            bridge._stop.set()  # exit the outer while on next iteration

    with patch.object(threading, 'Event', FakeEvent), \
         patch.object(bridge, '_send'), \
         patch.object(time, 'sleep', side_effect=sleep_side_effect):
        # Wire the per-test side-effect BEFORE the loop starts (so
        # the first probe already uses our results, not the default
        # timeout lambda).
        current_wait_fn[0] = wait_side_effect
        bridge._keepalive_loop()


def test_keepalive_1_failure_no_reconnect(bridge):
    """1 consecutive failure: counter=1, ws NOT closed."""
    _run_n_keepalive_cycles(bridge, 1, [False])
    assert bridge._consecutive_keepalive_failures == 1
    bridge._ws.close.assert_not_called()


def test_keepalive_2_failures_no_reconnect(bridge):
    """2 consecutive failures: counter=2, ws NOT closed."""
    _run_n_keepalive_cycles(bridge, 2, [False, False])
    assert bridge._consecutive_keepalive_failures == 2
    bridge._ws.close.assert_not_called()


def test_keepalive_3_failures_force_reconnect(bridge):
    """3 consecutive failures: counter reset to 0, ws IS closed once."""
    _run_n_keepalive_cycles(bridge, 3, [False, False, False])
    # Counter resets to 0 after we force a reconnect (so a future
    # probe starts fresh, not still "3 strikes")
    assert bridge._consecutive_keepalive_failures == 0
    bridge._ws.close.assert_called_once()


def test_keepalive_success_resets_counter(bridge):
    """2 failures + 1 success: counter reset to 0, ws NOT closed.

    This is the important case that protects against misfire: a
    single successful probe in the middle must NOT keep us one
    strike away from a forced reconnect. The new "counter=0 on
    success" line guards that.
    """
    _run_n_keepalive_cycles(bridge, 3, [False, False, True])
    assert bridge._consecutive_keepalive_failures == 0
    bridge._ws.close.assert_not_called()


def test_keepalive_close_raising_does_not_crash(bridge):
    """3 failures where _ws.close() itself raises: swallow and continue.

    Defensive: a buggy close() (e.g. websocket-client throwing on a
    half-closed socket) must not tear down the whole keepalive
    thread. The except-clause wraps close() in its own try/except.
    """
    bridge._ws.close.side_effect = Exception('close() exploded')
    _run_n_keepalive_cycles(bridge, 3, [False, False, False])
    assert bridge._consecutive_keepalive_failures == 0
    bridge._ws.close.assert_called_once()  # it was attempted even if it raised


def test_keepalive_first_cycle_starts_at_zero(bridge):
    """The counter defaults to 0 on a fresh bridge, not 3.

    Regression guard: if someone sets the default to 3 in __init__,
    the very first keepalive failure would force a reconnect.
    """
    assert bridge._consecutive_keepalive_failures == 0
