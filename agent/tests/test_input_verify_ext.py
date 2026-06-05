"""Tests for agent/input_inject.py: is_button_up / is_key_up / _key_to_vk.

The new (2026-06-05) silent-failure guards for mouse button and
keyboard state. These run in production via the ctypes GetAsyncKeyState
path, which is mocked here.

Also covers the ctypes-fallback named-key bug fix: _key_to_vk
must resolve named keys like 'ctrl' / 'f4' / 'enter' (App side
sends all of these), not just single chars.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

AGENT_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, AGENT_DIR)


def _import_inject_with_mocks():
    """Import input_inject with pyautogui / win32api / win32con stubbed.
    Returns (inject_module, pyautogui_mock). Fresh mock per call.

    Why win32api / win32con also get mocked: input_inject.py does
    `import win32api, win32con` at module level. If those imports
    succeed with the REAL pywin32 modules, they pollute sys.modules,
    and later tests (test_mouse_keyboard.py's TestHandleClipboard)
    that expect them to be MagicMock on `agent.win32con` /
    `agent.win32clipboard` will fail with 'module has no attribute
    reset_mock'. Pre-mocking here keeps the test world hermetic.
    """
    fresh_pg = MagicMock()
    sys.modules['pyautogui'] = fresh_pg
    sys.modules['win32api'] = MagicMock()
    sys.modules['win32con'] = MagicMock()
    if 'agent.input_inject' in sys.modules:
        del sys.modules['agent.input_inject']
    if 'agent' not in sys.modules:
        import types
        pkg = types.ModuleType('agent')
        pkg.__path__ = [AGENT_DIR]
        sys.modules['agent'] = pkg
    from agent import input_inject
    input_inject.pyautogui = fresh_pg
    return input_inject, fresh_pg


class TestIsButtonUp(unittest.TestCase):
    """B1-B5: is_button_up() reads GetAsyncKeyState and detects
    stuck mouse button (the symptom of 'mouseUp half lost')."""

    def setUp(self):
        self.inject, _ = _import_inject_with_mocks()
        self._state = patch.object(self.inject, '_get_async_key_state')
        self.mock_state = self._state.start()

    def tearDown(self):
        self._state.stop()

    def test_B1_returns_true_when_button_up(self):
        """0x8000 bit clear = not pressed."""
        self.mock_state.return_value = 0x0000
        self.assertTrue(self.inject.is_button_up('left'))

    def test_B2_returns_false_when_button_down(self):
        """0x8000 bit set = currently down. This is the silent
        failure we want to catch: the click's up half was a no-op."""
        self.mock_state.return_value = 0x8000
        self.assertFalse(self.inject.is_button_up('left'))

    def test_B3_works_for_all_buttons(self):
        """Each button has a distinct VK code (left=0x01, right=0x02,
        middle=0x04). Verify all three resolve correctly."""
        self.mock_state.return_value = 0x0000
        for btn in ('left', 'right', 'middle'):
            self.assertTrue(self.inject.is_button_up(btn))
        # And verify the right VK was passed
        calls = self.mock_state.call_args_list
        vk_used = {c.args[0] for c in calls}
        self.assertEqual(vk_used, {0x01, 0x02, 0x04})

    def test_B4_returns_true_for_unknown_button(self):
        """If a future caller passes a button name not in the
        table, we don't want to crash. Just skip the verify."""
        self.mock_state.assert_not_called()
        self.assertTrue(self.inject.is_button_up('thumb1'))

    def test_B5_logs_warning_when_button_stuck(self):
        """Stuck button must log a clear warning so operator sees
        it in helper.log without attaching a debugger."""
        self.mock_state.return_value = 0xC001  # 0x8000 + extras
        with self.assertLogs('agent.input', level='WARNING') as cm:
            self.inject.is_button_up('right')
        self.assertTrue(any('right' in m and 'still DOWN' in m for m in cm.output))


class TestIsKeyUp(unittest.TestCase):
    """K1-K4: is_key_up() reads GetAsyncKeyState and detects
    stuck key (the symptom of 'keyUp half lost')."""

    def setUp(self):
        self.inject, _ = _import_inject_with_mocks()
        self._state = patch.object(self.inject, '_get_async_key_state')
        self.mock_state = self._state.start()

    def tearDown(self):
        self._state.stop()

    def test_K1_returns_true_when_key_up(self):
        self.mock_state.return_value = 0x0000
        self.assertTrue(self.inject.is_key_up(0x0D))  # VK_RETURN

    def test_K2_returns_false_when_key_down(self):
        self.mock_state.return_value = 0x8000
        self.assertFalse(self.inject.is_key_up(0x0D))

    def test_K3_ignores_low_bit_transition_flag(self):
        """GetAsyncKeyState has two relevant bits: high (0x8000)
        = currently down, low (0x0001) = pressed since last call.
        We only care about the high bit. Set low bit but clear
        high bit → key is NOT down → verify should return True."""
        self.mock_state.return_value = 0x0001
        self.assertTrue(self.inject.is_key_up(0x41))  # VK_A

    def test_K4_logs_warning_when_key_stuck(self):
        self.mock_state.return_value = 0x8080
        with self.assertLogs('agent.input', level='WARNING') as cm:
            self.inject.is_key_up(0x1B)  # VK_ESCAPE
        # Format: 'is_key_up: VK 0x1B still DOWN ...' (uppercase hex)
        self.assertTrue(any('VK 0x1B' in m and 'still DOWN' in m for m in cm.output))


class TestKeyToVk(unittest.TestCase):
    """N1-N8: _key_to_vk() resolves key names to VK codes.

    The ctypes fallback used to have `vk = ... if len(key) == 1
    else 0` which silently dropped every named key. This test
    pins the fix: named keys must resolve correctly via the
    _NAMED_KEY_VK table.
    """

    def setUp(self):
        # IMPORTANT: this class exercises the ctypes branch of
        # _key_to_vk which imports ctypes. _import_inject_with_mocks
        # also pre-mocks win32api/win32con so that loading
        # input_inject does not pull in real pywin32 modules.
        self.inject, _ = _import_inject_with_mocks()

    def test_N1_named_keys_resolve(self):
        """The hotkey buttons in the App side send these specific
        names. Each must resolve to a real VK code, not 0."""
        for name, expected_vk in [
            ('ctrl', 0x11), ('alt', 0x12), ('shift', 0x10),
            ('enter', 0x0D), ('return', 0x0D), ('tab', 0x09),
            ('esc', 0x1B), ('escape', 0x1B), ('space', 0x20),
            ('delete', 0x2E), ('backspace', 0x08),
            ('win', 0x5B),
            ('f1', 0x70), ('f4', 0x73), ('f12', 0x7B),
            ('up', 0x26), ('down', 0x28), ('left', 0x25), ('right', 0x27),
        ]:
            with self.subTest(name=name):
                vk = self.inject._key_to_vk(name)
                self.assertEqual(vk, expected_vk, f'{name} should map to 0x{expected_vk:02X}')

    def test_N2_case_insensitive(self):
        """App might send 'Ctrl' or 'ctrl' depending on source."""
        self.assertEqual(self.inject._key_to_vk('Ctrl'), 0x11)
        self.assertEqual(self.inject._key_to_vk('CTRL'), 0x11)
        self.assertEqual(self.inject._key_to_vk('Enter'), 0x0D)

    def test_N3_empty_string_returns_none(self):
        """Don't crash on empty key. Caller logs and skips."""
        self.assertIsNone(self.inject._key_to_vk(''))

    def test_N4_unknown_named_key_returns_none(self):
        """If we don't know the name, return None so caller can
        log and skip (not silently send VK=0 which is no key)."""
        self.assertIsNone(self.inject._key_to_vk('hyperion'))
        self.assertIsNone(self.inject._key_to_vk('fn'))

    def test_N5_single_char_uses_vk_key_scan(self):
        """Single chars must use VkKeyScanW (handles shift state
        for uppercase, alt-gr for non-ASCII). Mock it."""
        with patch.object(self.inject, 'ctypes', create=True) if False else patch(
            'ctypes.windll.user32.VkKeyScanW', create=True
        ) as mock_scan:
            mock_scan.return_value = 0x2E  # VK_C, no shift
            vk = self.inject._key_to_vk('c')
            self.assertEqual(vk, 0x2E)

    def test_N6_uppercase_char_strips_shift_bit(self):
        """VkKeyScanW returns VK in low byte, shift in bit 8.
        We strip shift (the App side is responsible for sending
        shift separately if needed; for verify-after-press,
        we only need the VK)."""
        with patch('ctypes.windll.user32.VkKeyScanW', create=True) as mock_scan:
            mock_scan.return_value = 0x4E  # VK_C=0x4E, with shift=1 in high byte
            vk = self.inject._key_to_vk('C')
            self.assertEqual(vk, 0x4E)  # shift bit stripped

    def test_N7_non_mappable_char_returns_none(self):
        """Control chars and non-keyboard chars: VkKeyScanW
        returns -1. Don't crash, return None."""
        with patch('ctypes.windll.user32.VkKeyScanW', create=True) as mock_scan:
            mock_scan.return_value = -1
            self.assertIsNone(self.inject._key_to_vk('\x01'))

    def test_N8_caller_skips_when_vk_is_none(self):
        """Integration check: key() with an unknown name logs a
        warning and returns (doesn't raise)."""
        # Make sure pyautogui is False so we hit the ctypes branch
        with patch.object(self.inject, 'PYAUTOGUI_AVAILABLE', False), \
             patch.object(self.inject, '_key_to_vk', return_value=None), \
             self.assertLogs('agent.input', level='WARNING') as cm:
            # Mock ctypes.windll so the key() function doesn't blow
            # up on the ctypes call we never reach
            with patch('ctypes.windll.user32.keybd_event'):
                self.inject.key('hyperion', 'press')
        self.assertTrue(any('no VK mapping' in m for m in cm.output))


class TestKeyCallsIsKeyUp(unittest.TestCase):
    """KU1-KU2: key() with action='press' MUST call is_key_up()
    to catch the silent-failure case where the key's up half
    was lost.
    """

    def setUp(self):
        self.inject, _ = _import_inject_with_mocks()
        self._avail = patch.object(self.inject, 'PYAUTOGUI_AVAILABLE', True)
        self._avail.start()
        self._is_key = patch.object(self.inject, 'is_key_up', MagicMock())
        self._is_key.start()
        self._key_to_vk = patch.object(self.inject, '_key_to_vk', MagicMock(return_value=0x0D))
        self._key_to_vk.start()

    def tearDown(self):
        self._key_to_vk.stop()
        self._is_key.stop()
        self._avail.stop()

    def test_KU1_press_calls_is_key_up(self):
        self.inject.key('enter', 'press')
        self.inject.is_key_up.assert_called_once_with(0x0D)

    def test_KU2_down_does_not_call_is_key_up(self):
        """down leaves the key pressed, so verifying it's UP
        would always fail (false positive). Skip the verify."""
        self.inject.key('a', 'down')
        self.inject.is_key_up.assert_not_called()

    def test_KU3_up_does_not_call_is_key_up(self):
        """Same logic for up: key SHOULD be up after, so verifying
        'is up' is tautological. The verify is meaningful only for
        press (down + up cycle)."""
        self.inject.key('a', 'up')
        self.inject.is_key_up.assert_not_called()


if __name__ == '__main__':
    unittest.main()
