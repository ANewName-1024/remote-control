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
        self._upload_p = patch.object(self.agent, 'handle_file_upload')
        self._clipboard_p = patch.object(self.agent, 'handle_clipboard')
        self._thread_p = patch.object(self.agent.threading, 'Thread')
        self._mouse = self._mouse_p.start()
        self._key = self._key_p.start()
        self._download = self._download_p.start()
        self._upload = self._upload_p.start()
        self._clipboard = self._clipboard_p.start()
        self._thread = self._thread_p.start()

    def tearDown(self):
        self._mouse_p.stop()
        self._key_p.stop()
        self._download_p.stop()
        self._upload_p.stop()
        self._thread_p.stop()
        self._clipboard_p.stop()

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
        """D16: GAP-1 fix — agent now handles file_request:upload via handle_file_upload (inline, not thread)."""
        self.app._on_message({
            'type': 'file_request', 'action': 'upload',
            'path': 'docs/x.txt', 'filename': 'x.txt', 'session': 's1',
            'chunk': 'aGVsbG8=', 'chunkIdx': 0, 'isLast': True
        })
        # Upload is stateful across chunks, so it runs inline (no thread).
        self._thread.assert_not_called()
        # But handle_file_upload is called with the full message.
        self._upload.assert_called_once()
        call_msg = self._upload.call_args.args[0]
        self.assertEqual(call_msg['action'], 'upload')
        self.assertEqual(call_msg['filename'], 'x.txt')
        self.assertEqual(call_msg['chunk'], 'aGVsbG8=')

    def test_D16b_clipboard_dispatched(self):
        """D16b: GAP-3 fix — agent now handles clipboard via handle_clipboard (inline, no thread)."""
        self.app._on_message({
            'type': 'clipboard', 'action': 'set', 'content': 'hello'
        })
        self._thread.assert_not_called()
        self._clipboard.assert_called_once()
        call_msg = self._clipboard.call_args.args[0]
        self.assertEqual(call_msg['action'], 'set')
        self.assertEqual(call_msg['content'], 'hello')

    def test_D16c_clipboard_get_dispatched(self):
        """D16c: 'get' action also dispatched to handle_clipboard."""
        self.app._on_message({'type': 'clipboard', 'action': 'get'})
        self._clipboard.assert_called_once()
        call_msg = self._clipboard.call_args.args[0]
        self.assertEqual(call_msg['action'], 'get')

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


class TestHandleFileUpload(unittest.TestCase):
    """GAP-1 fix: handle_file_upload — chunked file upload from web client.

    Covers:
    - U1: single-chunk upload (chunkIdx=0, isLast=True)
    - U2: multi-chunk upload appends in order
    - U3: unsafe path (..) is rejected, no file written
    - U4: absolute path (C:\\...) is rejected
    - U5: out-of-order first chunk (no chunkIdx=0) is skipped
    - U6: result callback includes ok=True on success / ok=False on rejection
    """

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        # Sandbox the upload root so we don't touch the real APPDATA.
        self.tmp_root = tempfile.mkdtemp(prefix='rc-upload-')
        self._root_p = patch.object(self.agent, 'UPLOAD_ROOT', self.tmp_root)
        self._root_p.start()
        # Clear in-progress upload sessions between tests.
        self.agent.UPLOAD_SESSIONS.clear()
        self.sent = []

    def tearDown(self):
        self._root_p.stop()
        import shutil
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def _msg(self, filename, target_rel, b64, chunk_idx, is_last, total=None):
        m = {
            'type': 'file_request', 'action': 'upload',
            'session': f'ul_{chunk_idx}',
            'path': target_rel, 'filename': filename,
            'chunk': b64, 'chunkIdx': chunk_idx, 'isLast': is_last,
        }
        if total is not None:
            m['totalChunks'] = total
        return m

    def test_U1_single_chunk_upload(self):
        """U1: one-shot upload writes the file and emits ok=True result."""
        payload = base64.b64encode(b'hello world').decode('ascii')
        self.agent.handle_file_upload(
            self._msg('hi.txt', 'hi.txt', payload, 0, True),
            lambda m: self.sent.append(m)
        )
        target = os.path.join(self.tmp_root, 'hi.txt')
        self.assertTrue(os.path.isfile(target), f"file should be written at {target}")
        with open(target, 'rb') as f:
            self.assertEqual(f.read(), b'hello world')
        # Result callback
        results = [m for m in self.sent if m.get('type') == 'file_request_result']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['bytes'], len(b'hello world'))
        # Session cleaned up
        self.assertEqual(self.agent.UPLOAD_SESSIONS, {})

    def test_U2_multi_chunk_appends_in_order(self):
        """U2: chunks with different chunkIdx append to the same file in order."""
        chunks = [b'AAA', b'BBB', b'CCC']
        for i, c in enumerate(chunks):
            self.agent.handle_file_upload(
                self._msg('big.bin', 'sub/big.bin', base64.b64encode(c).decode('ascii'), i, i == len(chunks) - 1, total=len(chunks)),
                lambda m: self.sent.append(m)
            )
        target = os.path.join(self.tmp_root, 'sub', 'big.bin')
        self.assertTrue(os.path.isfile(target), f"file should be written at {target}")
        with open(target, 'rb') as f:
            self.assertEqual(f.read(), b'AAABBBCCC')
        # One result emitted (only on the isLast chunk)
        results = [m for m in self.sent if m.get('type') == 'file_request_result']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['bytes'], 9)

    def test_U3_unsafe_traversal_rejected(self):
        """U3: '..' in target path is rejected, no file written."""
        # Sandbox escape attempt: write outside tmp_root
        outside = os.path.join(self.tmp_root, '..', 'evil.txt')
        # Normalize: '..' should map under tmp_root (or get rejected)
        # Either way, the file should NOT end up outside tmp_root.
        # The validator rejects '..' outright, so the file shouldn't be written anywhere.
        self.agent.handle_file_upload(
            self._msg('evil.txt', '../evil.txt', base64.b64encode(b'pwned').decode('ascii'), 0, True),
            lambda m: self.sent.append(m)
        )
        # No file should be written inside the sandbox either.
        self.assertFalse(os.path.exists(outside), f"file should not be written outside sandbox: {outside}")
        # Result should be ok=False
        results = [m for m in self.sent if m.get('type') == 'file_request_result']
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['ok'])
        self.assertIn('Unsafe', results[0].get('error', ''))

    def test_U4_absolute_path_rejected(self):
        """U4: absolute path (C:\\foo) is rejected, no file written."""
        self.agent.handle_file_upload(
            self._msg('foo.txt', 'C:/Windows/System32/drivers/etc/foo.txt',
                      base64.b64encode(b'pwned').decode('ascii'), 0, True),
            lambda m: self.sent.append(m)
        )
        results = [m for m in self.sent if m.get('type') == 'file_request_result']
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['ok'])
        # Nothing written in sandbox
        self.assertEqual(os.listdir(self.tmp_root), [])

    def test_U5_out_of_order_first_chunk_skipped(self):
        """U5: if first seen chunkIdx > 0, it's silently skipped (no new session)."""
        # No chunk 0 first; this should be skipped.
        self.agent.handle_file_upload(
            self._msg('late.bin', 'late.bin', base64.b64encode(b'late').decode('ascii'), 2, True),
            lambda m: self.sent.append(m)
        )
        # No file written
        self.assertFalse(os.path.exists(os.path.join(self.tmp_root, 'late.bin')))
        # No result emitted either (silently dropped)
        results = [m for m in self.sent if m.get('type') == 'file_request_result']
        self.assertEqual(len(results), 0)
        # And no lingering session
        self.assertEqual(self.agent.UPLOAD_SESSIONS, {})

    def test_U6_size_limit_enforced(self):
        """U6: a single chunk that would push the file over UPLOAD_MAX_BYTES is rejected."""
        # Use a tiny cap for the test.
        with patch.object(self.agent, 'UPLOAD_MAX_BYTES', 4):
            # 1st chunk: 3 bytes, OK
            self.agent.handle_file_upload(
                self._msg('big.bin', 'big.bin', base64.b64encode(b'AAA').decode('ascii'), 0, False),
                lambda m: self.sent.append(m)
            )
            # 2nd chunk: 5 more bytes -> would exceed 4
            self.agent.handle_file_upload(
                self._msg('big.bin', 'big.bin', base64.b64encode(b'BBBBB').decode('ascii'), 1, True),
                lambda m: self.sent.append(m)
            )
        # File should be either absent or contain only the 3 bytes (cap was hit).
        target = os.path.join(self.tmp_root, 'big.bin')
        if os.path.exists(target):
            with open(target, 'rb') as f:
                self.assertLessEqual(len(f.read()), 4)
        # A rejection result should have been emitted
        rejects = [m for m in self.sent if m.get('type') == 'file_request_result' and not m.get('ok')]
        self.assertTrue(any('too large' in r.get('error', '').lower() for r in rejects),
                        f"expected 'too large' rejection, got: {self.sent}")
        # Session cleaned up after rejection
        self.assertEqual(self.agent.UPLOAD_SESSIONS, {})


class TestHandleClipboard(unittest.TestCase):
    """GAP-3 fix: handle_clipboard — set/get Windows clipboard from web client.

    Covers:
    - CB1: set writes via win32clipboard and returns ok=True
    - CB2: set with empty content still writes
    - CB3: get reads via win32clipboard and returns content
    - CB4: get with CF_UNICODETEXT returning None falls back to CF_TEXT
    - CB5: set error from win32 returns ok=False + error message
    - CB6: unknown action returns ok=False with error
    - CB7: WIN32_AVAILABLE=False returns ok=False with not-available error
    """

    @classmethod
    def setUpClass(cls):
        cls.agent, _ = try_import_agent()

    def setUp(self):
        self.sent = []
        # Reset the MagicMock for win32clipboard (try_import_agent pre-injects it)
        # but preserve any pre-set return values from earlier tests in this class.
        # We re-create the mock for full isolation.
        if hasattr(self.agent, 'win32clipboard'):
            self.agent.win32clipboard.reset_mock()
        if hasattr(self.agent, 'win32con'):
            self.agent.win32con.reset_mock()

    def _send(self, m):
        self.sent.append(m)

    # ---------- CB1: set ----------
    def test_CB1_set_writes_and_returns_ok(self):
        """CB1: 'set' action calls win32clipboard and returns ok=True with bytes."""
        self.agent.win32clipboard.GetClipboardData = MagicMock(return_value=None)  # unused
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'set', 'content': 'hello'},
            self._send
        )
        self.agent.win32clipboard.OpenClipboard.assert_called_once()
        self.agent.win32clipboard.SetClipboardText.assert_called_once_with('hello')
        self.agent.win32clipboard.CloseClipboard.assert_called_once()
        results = [m for m in self.sent if m['type'] == 'clipboard' and m['action'] == 'set']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['bytes'], 5)  # len('hello')

    # ---------- CB2: set empty ----------
    def test_CB2_set_empty(self):
        """CB2: empty string still calls SetClipboardText('') and returns bytes=0."""
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'set', 'content': ''},
            self._send
        )
        self.agent.win32clipboard.SetClipboardText.assert_called_once_with('')
        results = [m for m in self.sent if m['type'] == 'clipboard' and m['action'] == 'set']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['bytes'], 0)

    # ---------- CB3: get ----------
    def test_CB3_get_reads_unicode(self):
        """CB3: 'get' action reads CF_UNICODETEXT and returns content."""
        self.agent.win32con.CF_UNICODETEXT = 13  # real value
        self.agent.win32clipboard.GetClipboardData = MagicMock(return_value='remote text')
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'get'},
            self._send
        )
        self.agent.win32clipboard.OpenClipboard.assert_called_once()
        self.agent.win32clipboard.GetClipboardData.assert_called_once_with(13)
        self.agent.win32clipboard.CloseClipboard.assert_called_once()
        results = [m for m in self.sent if m['type'] == 'clipboard' and m['action'] == 'get']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['content'], 'remote text')

    # ---------- CB4: get falls back to CF_TEXT ----------
    def test_CB4_get_ansi_fallback(self):
        """CB4: if CF_UNICODETEXT returns None, fall back to CF_TEXT."""
        self.agent.win32con.CF_UNICODETEXT = 13
        self.agent.win32con.CF_TEXT = 1
        # First call (UNICODE) returns None; second (ANSI) returns 'ansi text'
        self.agent.win32clipboard.GetClipboardData = MagicMock(side_effect=[None, 'ansi text'])
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'get'},
            self._send
        )
        self.assertEqual(self.agent.win32clipboard.GetClipboardData.call_count, 2)
        results = [m for m in self.sent if m['type'] == 'clipboard' and m['action'] == 'get']
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['ok'])
        self.assertEqual(results[0]['content'], 'ansi text')

    # ---------- CB5: set error ----------
    def test_CB5_set_error(self):
        """CB5: win32 error during set returns ok=False + error message."""
        self.agent.win32clipboard.SetClipboardText = MagicMock(
            side_effect=OSError('access denied')
        )
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'set', 'content': 'x'},
            self._send
        )
        results = [m for m in self.sent if m['type'] == 'clipboard' and m['action'] == 'set']
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['ok'])
        self.assertIn('access denied', results[0]['error'])

    # ---------- CB6: unknown action ----------
    def test_CB6_unknown_action(self):
        """CB6: unknown action returns ok=False with error mentioning the bad action."""
        self.agent.handle_clipboard(
            {'type': 'clipboard', 'action': 'teleport'},
            self._send
        )
        results = [m for m in self.sent if m['type'] == 'clipboard']
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]['ok'])
        self.assertIn('teleport', results[0]['error'])

    # ---------- CB7: win32 not available ----------
    def test_CB7_no_win32(self):
        """CB7: when WIN32_AVAILABLE=False, returns ok=False with not-available error."""
        with patch.object(self.agent, 'WIN32_AVAILABLE', False):
            self.agent.handle_clipboard(
                {'type': 'clipboard', 'action': 'set', 'content': 'x'},
                self._send
            )
            self.agent.handle_clipboard(
                {'type': 'clipboard', 'action': 'get'},
                self._send
            )
        results = [m for m in self.sent if m['type'] == 'clipboard']
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertFalse(r['ok'])
            self.assertIn('not available', r['error'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
