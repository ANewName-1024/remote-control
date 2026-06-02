"""
Agent Input Simulation / Command / File Transfer Tests
Covers test_design.md §D (Agent protocol handling)

Tests parse_key, handle_mouse, handle_key, handle_hotkey, execute_command,
handle_file_download, _on_message dispatch, _get_machine_fingerprint,
get_or_create_credentials.

Strategy: mock optional deps (pyautogui, win32api, subprocess) to test on
any platform. Real deps only needed for integration / smoke tests.

Run: python -m unittest tests.test_mouse_keyboard -v
"""
import os
import sys
import json
import time
import unittest
import tempfile
import base64
import hashlib
from unittest.mock import patch, MagicMock, mock_open

# Add agent/ to path
AGENT_DIR = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, AGENT_DIR)


def try_import_agent():
    """Import agent.py with mocked optional deps so tests run on any platform.

    Returns (agent_module, deps_status_dict).
    """
    # Pre-mock modules that agent.py imports at module level
    mock_modules = {}
    for mod_name in [
        'pyautogui', 'win32api', 'win32con', 'win32gui', 'win32clipboard',
        'win32event', 'win32process', 'win32com', 'win32com.client',
        'pythoncom', 'mss', 'psutil', 'websocket'
    ]:
        if mod_name not in sys.modules:
            mock_modules[mod_name] = MagicMock()

    # Save original modules
    saved = {k: sys.modules.get(k) for k in mock_modules}
    sys.modules.update(mock_modules)

    try:
        # Now import agent
        import agent
        deps = {
            'PSUTIL_AVAILABLE': agent.PSUTIL_AVAILABLE,
            'MSS_AVAILABLE': agent.MSS_AVAILABLE,
            'PIL_AVAILABLE': agent.PIL_AVAILABLE,
            'PYAUTOGUI_AVAILABLE': agent.PYAUTOGUI_AVAILABLE,
            'WIN32_AVAILABLE': agent.WIN32_AVAILABLE,
            'WS_AVAILABLE': agent.WS_AVAILABLE,
            'PYTHONCOM_AVAILABLE': agent.PYTHONCOM_AVAILABLE,
        }
        return agent, deps
    finally:
        # Restore real modules if they existed
        for k, v in saved.items():
            if v is not None:
                sys.modules[k] = v


class TestAgentModule(unittest.TestCase):
    """Module-level sanity: agent.py imports, KEY_MAP populated, deps detected."""

    @classmethod
    def setUpClass(cls):
        cls.agent, cls.deps = try_import_agent()

    def test_module_imports(self):
        self.assertIsNotNone(self.agent, "agent.py should import without errors")

    def test_key_map_has_standard_keys(self):
        """D1: KEY_MAP covers enter/tab/esc/shift/ctrl/alt/win/etc."""
        km = self.agent.KEY_MAP
        for k in ['enter', 'tab', 'escape', 'shift', 'ctrl', 'alt', 'win',
                  'backspace', 'delete', 'up', 'down', 'left', 'right',
                  'home', 'end', 'pageup', 'pagedown', 'f1', 'f12', 'space']:
            self.assertIn(k, km, f"KEY_MAP missing standard key: {k}")
            self.assertIsInstance(km[k], int, f"KEY_MAP[{k}] should be int VK code")

    def test_key_map_hex_values(self):
        """D1b: known VK codes are correct."""
        self.assertEqual(self.agent.KEY_MAP['enter'], 0x0D)
        self.assertEqual(self.agent.KEY_MAP['tab'], 0x09)
        self.assertEqual(self.agent.KEY_MAP['escape'], 0x1B)
        self.assertEqual(self.agent.KEY_MAP['space'], 0x20)
        self.assertEqual(self.agent.KEY_MAP['f1'], 0x70)
        self.assertEqual(self.agent.KEY_MAP['f12'], 0x7B)


class TestParseKey(unittest.TestCase):
    """D2/D3: parse_key function."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def test_D02_named_key_lookup(self):
        """D2: 'enter' → 0x0D"""
        self.assertEqual(self.agent.parse_key('enter'), 0x0D)
        self.assertEqual(self.agent.parse_key('ctrl'), 0x11)

    def test_D02b_case_insensitive(self):
        self.assertEqual(self.agent.parse_key('ENTER'), 0x0D)
        self.assertEqual(self.agent.parse_key('Ctrl'), 0x11)

    def test_D02c_aliases(self):
        self.assertEqual(self.agent.parse_key('esc'), 0x1B)
        self.assertEqual(self.agent.parse_key('escape'), 0x1B)
        self.assertEqual(self.agent.parse_key('return'), 0x0D)
        self.assertEqual(self.agent.parse_key('del'), 0x2E)

    def test_D06b_single_char(self):
        """D2: 'a' → VkKeyScan result (we mock win32api)."""
        # With mocked win32api, VkKeyScan returns a MagicMock by default.
        # We configure it to return a specific value so we can assert.
        with patch.object(self.agent.win32api, 'VkKeyScan', return_value=0x41):
            result = self.agent.parse_key('a')
        self.assertEqual(result, 0x41, f"parse_key('a') should return low byte of VkKeyScan, got {result}")

    def test_D03_unknown_key_returns_none(self):
        """D3: unknown multi-char key returns None."""
        self.assertIsNone(self.agent.parse_key('fakethatdoesnotexist'))
        # Empty string has len 0, len(k) == 1 is False, k not in KEY_MAP
        self.assertIsNone(self.agent.parse_key(''))


class TestHandleMouse(unittest.TestCase):
    """D4/D5: handle_mouse coordinate clipping and action dispatch."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        # Reset pyautogui mock for each test
        self._pyautogui_patcher = patch.object(self.agent, 'pyautogui', MagicMock())
        self._pyautogui_patcher.start()
        self._size_patcher = patch.object(self.agent, 'get_screen_size', return_value=(1920, 1080))
        self._size_patcher.start()
        # Force PYAUTOGUI_AVAILABLE True for these tests
        self._avail_patcher = patch.object(self.agent, 'PYAUTOGUI_AVAILABLE', True)
        self._avail_patcher.start()

    def tearDown(self):
        self._pyautogui_patcher.stop()
        self._size_patcher.stop()
        self._avail_patcher.stop()

    def test_D04_clip_x_above_max(self):
        """D4: x > w-1 is clipped to w-1."""
        self.agent.handle_mouse(9999, 500, 'left', 'move')
        self.agent.pyautogui.moveTo.assert_called_with(1919, 500, duration=0)

    def test_D04b_clip_y_below_zero(self):
        self.agent.handle_mouse(500, -100, 'left', 'move')
        self.agent.pyautogui.moveTo.assert_called_with(500, 0, duration=0)

    def test_D05_move_action(self):
        self.agent.handle_mouse(100, 200, 'left', 'move')
        self.agent.pyautogui.moveTo.assert_called_with(100, 200, duration=0)

    def test_D05b_down_action_left(self):
        self.agent.handle_mouse(100, 200, 'left', 'down')
        self.agent.pyautogui.mouseDown.assert_called_with(100, 200, 'left')

    def test_D05c_down_action_right(self):
        self.agent.handle_mouse(100, 200, 'right', 'down')
        self.agent.pyautogui.mouseDown.assert_called_with(100, 200, 'right')

    def test_D05d_click_action(self):
        self.agent.handle_mouse(100, 200, 'left', 'click')
        self.agent.pyautogui.click.assert_called_with(100, 200, button='left')

    def test_D05e_double_click(self):
        self.agent.handle_mouse(100, 200, 'left', 'double_click')
        self.agent.pyautogui.doubleClick.assert_called_with(100, 200)

    def test_D05f_wheel(self):
        self.agent.handle_mouse(100, 200, 'left', 'wheel')
        self.agent.pyautogui.scroll.assert_called()

    def test_D05g_up_action(self):
        self.agent.handle_mouse(100, 200, 'right', 'up')
        self.agent.pyautogui.mouseUp.assert_called_with(100, 200, 'right')


class TestHandleKey(unittest.TestCase):
    """D6: handle_key down/press/up."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        self._pyautogui_patcher = patch.object(self.agent, 'pyautogui', MagicMock())
        self._pyautogui_patcher.start()
        self._avail_patcher = patch.object(self.agent, 'PYAUTOGUI_AVAILABLE', True)
        self._avail_patcher.start()

    def tearDown(self):
        self._pyautogui_patcher.stop()
        self._avail_patcher.stop()

    def test_D06_press_calls_down_then_up(self):
        self.agent.handle_key('a', 'press')
        self.agent.pyautogui.keyDown.assert_called_with('a')
        self.agent.pyautogui.keyUp.assert_called_with('a')

    def test_D06b_down_only(self):
        self.agent.pyautogui.reset_mock()
        self.agent.handle_key('ctrl', 'down')
        self.agent.pyautogui.keyDown.assert_called_with('ctrl')
        self.agent.pyautogui.keyUp.assert_not_called()

    def test_D06c_up_only(self):
        self.agent.pyautogui.reset_mock()
        self.agent.handle_key('ctrl', 'up')
        self.agent.pyautogui.keyUp.assert_called_with('ctrl')
        self.agent.pyautogui.keyDown.assert_not_called()

    def test_D06d_unknown_key_noop(self):
        self.agent.handle_key('xxnotreal', 'press')
        self.agent.pyautogui.keyDown.assert_not_called()


class TestHandleHotkey(unittest.TestCase):
    """D7: handle_hotkey invokes pyautogui.hotkey."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        self._pyautogui_patcher = patch.object(self.agent, 'pyautogui', MagicMock())
        self._pyautogui_patcher.start()
        self._avail_patcher = patch.object(self.agent, 'PYAUTOGUI_AVAILABLE', True)
        self._avail_patcher.start()

    def tearDown(self):
        self._pyautogui_patcher.stop()
        self._avail_patcher.stop()

    def test_D07_hotkey_passthrough(self):
        self.agent.handle_hotkey('ctrl', 'alt', 'del')
        self.agent.pyautogui.hotkey.assert_called_with('ctrl', 'alt', 'del')


class TestExecuteCommand(unittest.TestCase):
    """D8/D9: execute_command with mocked subprocess."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def test_D08_empty_cmd_sends_done(self):
        """D8: empty cmd → sends done immediately, no subprocess."""
        sent = []
        self.agent.execute_command('', 'sess-1', lambda m: sent.append(m))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0], {'type': 'output', 'session': 'sess-1', 'data': '', 'done': True})

    def test_D09_chinese_output(self):
        """D9: utf-8 decoded output is sent correctly."""
        sent = []
        fake_proc = MagicMock()
        fake_proc.stdout.read.side_effect = ['你好世界\n'.encode('utf-8'), b'']
        fake_proc.wait.return_value = 0
        with patch.object(self.agent.subprocess, 'Popen', return_value=fake_proc):
            self.agent.execute_command('echo 中文', 'sess-2', lambda m: sent.append(m))
        # Should have at least one output line with 'data' field
        outputs = [m for m in sent if m.get('type') == 'output']
        self.assertTrue(any('你好世界' in o.get('data', '') for o in outputs),
                        f"Chinese output not found in: {sent}")
        # Final message must be done=True
        self.assertTrue(outputs[-1].get('done'), f"Last output should be done: {sent}")


class TestHandleFileDownload(unittest.TestCase):
    """D10/D11: file download chunking and error handling."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def test_D10_nonexistent_file_sends_error(self):
        """D10: missing file → output message with error."""
        sent = []
        self.agent.handle_file_download(
            'C:/nonexistent/path/file.txt', 'sess-3', 'file.txt', lambda m: sent.append(m)
        )
        self.assertEqual(len(sent), 1)
        self.assertIn('File not found', sent[0].get('data', ''))
        self.assertTrue(sent[0].get('done'))

    def test_D11_chunked_base64(self):
        """D11: real file → multiple file_chunk messages ending with done=True."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(b'A' * 100000)  # 100KB
            tmp = f.name
        try:
            sent = []
            self.agent.handle_file_download(tmp, 'sess-4', 'big.bin', lambda m: sent.append(m))
            chunks = [m for m in sent if m['type'] == 'file_chunk']
            self.assertGreater(len(chunks), 1, "should send multiple chunks for 100KB")
            self.assertTrue(chunks[-1]['done'], "last chunk should be done=True")
            # First chunk's base64 should decode to non-empty
            decoded = base64.b64decode(chunks[0]['chunk'])
            self.assertGreater(len(decoded), 0)
            # Total decoded size should match file size
            total = sum(len(base64.b64decode(c['chunk'])) for c in chunks if c['chunk'])
            self.assertEqual(total, 100000, f"total decoded {total} should equal 100000")
        finally:
            os.unlink(tmp)


class TestOnMessageDispatch(unittest.TestCase):
    """D12-D16: _on_message routes to correct handlers."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        # Build a minimal RemoteControlApp instance without init()
        self.app = self.agent.RemoteControlApp.__new__(self.agent.RemoteControlApp)
        self.app.connected = True
        self.app.authenticated = True
        self.app.ws_client = MagicMock()

        # Patch handlers
        self._mouse_p = patch.object(self.agent, 'handle_mouse')
        self._key_p = patch.object(self.agent, 'handle_key')
        self._download_p = patch.object(self.agent, 'handle_file_download')
        self._thread_p = patch.object(self.agent.threading, 'Thread')
        self._mouse = self._mouse_p.start()
        self._key = self._key_p.start()
        self._download = self._download_p.start()
        self._thread = self._thread_p.start()

    def tearDown(self):
        self._mouse_p.stop()
        self._key_p.stop()
        self._download_p.stop()
        self._thread_p.stop()

    def test_D12_mouse_dispatched(self):
        self.app._on_message({'type': 'mouse', 'x': 1, 'y': 2, 'button': 'left', 'action': 'click'})
        self._mouse.assert_called_once_with(1, 2, 'left', 'click')

    def test_D13_key_dispatched(self):
        self.app._on_message({'type': 'key', 'action': 'press', 'key': 'enter'})
        self._key.assert_called_once_with('enter', 'press')

    def test_D14_exec_spawns_thread(self):
        self.app._on_message({'type': 'exec', 'cmd': 'whoami', 'session': 's1'})
        self._thread.assert_called_once()
        # Verify daemon=True
        kwargs = self._thread.call_args.kwargs
        self.assertTrue(kwargs.get('daemon'), "exec thread should be daemon=True")

    def test_D15_file_request_download_spawns_thread(self):
        self.app._on_message({
            'type': 'file_request', 'action': 'download',
            'path': 'C:/x', 'filename': 'x', 'session': 's1'
        })
        self._thread.assert_called_once()
        # Thread is constructed with target=... as kwarg, not positional
        kwargs = self._thread.call_args.kwargs
        self.assertEqual(kwargs.get('target'), self.agent.handle_file_download,
                         f"thread target should be handle_file_download, got {kwargs}")

    def test_D16_file_request_upload_ignored(self):
        """D16: GAP-1 — agent does not implement file_request:upload. Verify it's silently dropped."""
        self.app._on_message({
            'type': 'file_request', 'action': 'upload',
            'path': 'C:/x', 'filename': 'x', 'session': 's1'
        })
        # No thread should be spawned
        self._thread.assert_not_called()
        # No error raised — just no-op

    def test_unknown_type_ignored(self):
        """Unknown message types don't crash _on_message."""
        # Should not raise
        self.app._on_message({'type': 'unknown_type', 'foo': 'bar'})
        self._mouse.assert_not_called()
        self._key.assert_not_called()


class TestFingerprintDeterminism(unittest.TestCase):
    """D17: _get_machine_fingerprint is deterministic per machine."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def test_D17_returns_16_hex(self):
        fp = self.agent._get_machine_fingerprint()
        self.assertIsInstance(fp, str)
        self.assertEqual(len(fp), 16, f"fingerprint should be 16 chars, got {len(fp)}")
        self.assertTrue(all(c in '0123456789abcdef' for c in fp),
                        f"fingerprint should be hex, got {fp}")

    def test_D17b_deterministic(self):
        fp1 = self.agent._get_machine_fingerprint()
        fp2 = self.agent._get_machine_fingerprint()
        self.assertEqual(fp1, fp2, "fingerprint should be deterministic across calls")


class TestCredentialsPersistence(unittest.TestCase):
    """D18: get_or_create_credentials persists and reuses."""

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # CONFIG_DIR and CONFIG_FILE are computed at module import time using
        # APPDATA, so we must patch them on the module directly (env var won't help).
        self._cfgdir_p = patch.object(self.agent, 'CONFIG_DIR',
                                       os.path.join(self.tmpdir, 'RemoteControlAgent'))
        self._cfgfile_p = patch.object(self.agent, 'CONFIG_FILE',
                                        os.path.join(self.tmpdir, 'RemoteControlAgent', 'agent.json'))
        self._cfgdir_p.start()
        self._cfgfile_p.start()

    def tearDown(self):
        self._cfgdir_p.stop()
        self._cfgfile_p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_D18_first_run_creates_credentials(self):
        aid, sec, url = self.agent.get_or_create_credentials()
        self.assertTrue(aid and len(aid) == 36, f"agent_id should be uuid (36 chars), got {aid}")
        self.assertTrue(sec and len(sec) >= 8, f"secret should be 8+ chars, got {sec}")
        # agent.json should be written
        cfg_path = os.path.join(self.tmpdir, 'RemoteControlAgent', 'agent.json')
        self.assertTrue(os.path.exists(cfg_path), f"agent.json should be written at {cfg_path}")
        with open(cfg_path) as f:
            cfg = json.load(f)
        self.assertEqual(cfg['agent_id'], aid)
        self.assertEqual(cfg['secret'], sec)

    def test_D18b_second_run_reuses(self):
        aid1, sec1, _ = self.agent.get_or_create_credentials()
        aid2, sec2, _ = self.agent.get_or_create_credentials()
        self.assertEqual(aid1, aid2, "agent_id should be stable across calls")
        self.assertEqual(sec1, sec2, "secret should be stable across calls")


if __name__ == '__main__':
    unittest.main(verbosity=2)
