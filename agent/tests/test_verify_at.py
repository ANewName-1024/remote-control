"""Tests for agent/input_inject.py: verify_at() and post-mouse verification.

verify_at() is the silent-failure guard for mouse injection. The unit
test exercises the cursor-mismatch path (the one that actually
catches Session 0 / UAC / display-lock bugs); a real desktop
verification is in agent/smoke_test_mouse.py.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

AGENT_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, AGENT_DIR)


def _import_inject_with_mocks():
    """Import input_inject with pyautogui stubbed so the module
    loads without a real display. Returns (inject_module, pyautogui_mock).

    Always injects a fresh MagicMock into sys.modules['pyautogui']
    and into input_inject's namespace. Previous test files (notably
    test_mouse_keyboard.py) leave a shared MagicMock in
    sys.modules which has per-test state baked in from prior
    test runs; reusing that state made V1/V2 see stale return
    values. Fresh mock per test = hermetic.
    """
    fresh_pg = MagicMock()
    sys.modules['pyautogui'] = fresh_pg
    if 'agent.input_inject' in sys.modules:
        del sys.modules['agent.input_inject']
    if 'agent' not in sys.modules:
        import types
        pkg = types.ModuleType('agent')
        pkg.__path__ = [AGENT_DIR]
        sys.modules['agent'] = pkg
    from agent import input_inject
    # Re-bind input_inject's module-level pyautogui to the fresh
    # mock. (The `import pyautogui` inside input_inject already
    # picked up sys.modules['pyautogui'], but setUp is called
    # multiple times and we want each test to start clean.)
    input_inject.pyautogui = fresh_pg
    return input_inject, fresh_pg


class TestVerifyAt(unittest.TestCase):
    """V1-V4: verify_at() reads cursor position and detects mismatch."""

    def setUp(self):
        self.inject, self.pg = _import_inject_with_mocks()
        # Force PYAUTOGUI_AVAILABLE True for these tests
        self._avail = patch.object(self.inject, 'PYAUTOGUI_AVAILABLE', True)
        self._avail.start()

    def tearDown(self):
        self._avail.stop()

    def test_V1_returns_true_when_cursor_at_target(self):
        self.pg.position.return_value = (100, 200)
        self.assertTrue(self.inject.verify_at(100, 200))

    def test_V2_returns_true_within_tolerance(self):
        # 1 pixel off in each direction is OK (sub-pixel rounding)
        self.pg.position.return_value = (101, 201)
        self.assertTrue(self.inject.verify_at(100, 200, tolerance=2))

    def test_V3_returns_false_when_cursor_wrong(self):
        # The bug we're guarding against: SendInput no-op'd and
        # the cursor is still at (50, 50) instead of (100, 200).
        self.pg.position.return_value = (50, 50)
        self.assertFalse(self.inject.verify_at(100, 200))

    def test_V4_logs_warning_on_mismatch(self):
        """Mismatch must log a warning so the operator sees it in
        helper.log without having to attach a debugger."""
        self.pg.position.return_value = (0, 0)
        with self.assertLogs('agent.input', level='WARNING') as cm:
            self.inject.verify_at(500, 500)
        self.assertTrue(any('verify_at MISMATCH' in m for m in cm.output))

    def test_V5_handles_position_read_exception(self):
        """If pyautogui.position() raises (e.g. headless test env),
        verify_at must NOT crash the call site."""
        self.pg.position.side_effect = RuntimeError('no display')
        self.assertFalse(self.inject.verify_at(100, 200))

    def test_V6_no_pyautogui_skips_verify(self):
        """When pyautogui is unavailable, verify_at returns True
        (we don't know the answer, but we don't crash either).
        The ctypes path's truthiness is the caller's problem."""
        with patch.object(self.inject, 'PYAUTOGUI_AVAILABLE', False):
            self.assertTrue(self.inject.verify_at(100, 200))


class TestMouseCallsVerifyAt(unittest.TestCase):
    """V7-V8: mouse() with action='move' MUST call verify_at().

    This is the wiring test that makes the silent-failure guard
    actually fire in production. Without it, verify_at is dead
    code.
    """

    def setUp(self):
        self.inject, self.pg = _import_inject_with_mocks()
        self._avail = patch.object(self.inject, 'PYAUTOGUI_AVAILABLE', True)
        self._avail.start()
        # verify_at is module-level; patch it to a MagicMock so we
        # can assert it was called without re-implementing the
        # cursor math.
        self._verify = patch.object(self.inject, 'verify_at', MagicMock())
        self._verify.start()

    def tearDown(self):
        self._verify.stop()
        self._avail.stop()

    def test_V7_move_calls_verify(self):
        self.inject.mouse(123, 456, 'left', 'move', (1920, 1080))
        self.inject.verify_at.assert_called_once_with(123, 456)

    def test_V8_click_does_not_call_verify(self):
        """A click without a preceding move lands at the cursor's
        current (unknown) position, so verify-after-click is
        meaningless. We only verify on 'move'."""
        self.inject.mouse(123, 456, 'left', 'click', (1920, 1080))
        self.inject.verify_at.assert_not_called()

    def test_V9_down_does_not_call_verify(self):
        self.inject.mouse(123, 456, 'left', 'down', (1920, 1080))
        self.inject.verify_at.assert_not_called()

    def test_V10_up_does_not_call_verify(self):
        self.inject.mouse(123, 456, 'left', 'up', (1920, 1080))
        self.inject.verify_at.assert_not_called()

    def test_V11_wheel_does_not_call_verify(self):
        # Wheel sends delta in y, not a target position
        self.inject.mouse(100, -120, 'left', 'wheel', (1920, 1080))
        self.inject.verify_at.assert_not_called()


if __name__ == '__main__':
    unittest.main()
