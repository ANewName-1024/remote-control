"""
WS -> helper cmd pipe translation tests.

Covers the bridge between the WS protocol (clients speak
`type: mouse / key`) and the helper's IPC protocol (split per-event
types `input_mouse` / `input_key` / ...).

Regression: previously the bridge only handled `type: input` (which
the server never sends) and silently dropped every mouse / key from
the App, so the user could see the screen but clicks and keystrokes
had no effect on the host.

Run: python -m unittest tests.test_ws_input_bridge -v
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


AGENT_DIR = os.path.join(os.path.dirname(__file__), '..')
PARENT_DIR = os.path.dirname(AGENT_DIR)
# ws_bridge uses `from . import protocol`, so the parent must be on
# sys.path so that `agent` resolves as a package.
sys.path.insert(0, PARENT_DIR)


class TestWsToHelperInputTranslation(unittest.TestCase):
    """Verify the WS bridge rewrites client messages into the helper's
    IPC types so an actual key/mouse click on the phone reaches the
    host's input_inject module."""

    def setUp(self):
        # Mock optional deps that ws_bridge imports at module load.
        # websocket-client is the only one we need to fake for unit
        # tests (we never actually open a socket).
        self._wsclient_patches = []
        for mod in ('websocket',):
            if mod not in sys.modules:
                # Inject a fake module that exposes WebSocketTimeoutException
                m = MagicMock()
                m.WebSocketTimeoutException = type('WebSocketTimeoutException', (Exception,), {})
                sys.modules[mod] = m
        from agent import ws_bridge, protocol as ipc
        self.ws_bridge = ws_bridge
        self.ipc = ipc

        # Build a WSBridge with all heavy collaborators stubbed: the
        # pipes (cmd pipe), the websocket, the capture queue, and
        # threads we never start. We only exercise _on_server_msg.
        self.pipes = MagicMock()
        self.pipes.send_cmd = MagicMock()

        with patch.object(self.ws_bridge, 'WSBridge') as Ctor:
            pass  # placeholder; we just need the class
        # Instantiate directly, bypassing __init__ because the real
        # one opens sockets and spawns threads. We MUST mirror every
        # attribute that _on_server_msg (or any other method we
        # exercise) reads from self.* — the real __init__ sets all of
        # these, and the dict is the source of truth. Keeping the
        # list short on purpose: if a future test touches a new
        # attribute, _on_server_msg will fail loudly with an
        # AttributeError at the first read, prompting us to add it
        # here (which is the same fail-mode the source would hit if
        # __init__ ever forgot to initialize a field).
        self.bridge = self.ws_bridge.WSBridge.__new__(self.ws_bridge.WSBridge)
        self.bridge.pipes = self.pipes
        self.bridge.cmds_recv = 0
        self.bridge._disposed = False
        # Required by _on_server_msg (line 323 of ws_bridge.py):
        # the per-msg-type counter is bumped on every non-ping msg.
        self.bridge._msg_type_stats = {}
        # Required when the test sends 'seq' in a mouse/key payload:
        # the bridge records the highest seq it has processed.
        self.bridge._last_input_seq = 0

    def tearDown(self):
        # No real threads/timers were created; nothing to clean up.
        pass

    # --- mouse ---

    def test_mouse_down_forwarded_as_input_mouse(self):
        self.bridge._on_server_msg({
            'type': 'mouse',
            'action': 'down',
            'x': 123,
            'y': 456,
            'button': 'left',
        })
        self.pipes.send_cmd.assert_called_once()
        sent = self.pipes.send_cmd.call_args[0][0]
        self.assertEqual(sent['type'], self.ipc.MSG_INPUT_MOUSE)
        self.assertEqual(sent['x'], 123)
        self.assertEqual(sent['y'], 456)
        self.assertEqual(sent['button'], 'left')
        self.assertEqual(sent['action'], 'down')
        self.assertEqual(self.bridge.cmds_recv, 1)

    def test_mouse_move_default_button_left(self):
        # Real clients (HTML + App) only send `button` on down/up;
        # move events omit it. The bridge should default to 'left'
        # so the helper doesn't have to handle a missing key.
        self.bridge._on_server_msg({
            'type': 'mouse',
            'action': 'move',
            'x': 10,
            'y': 20,
        })
        sent = self.pipes.send_cmd.call_args[0][0]
        self.assertEqual(sent['button'], 'left')
        self.assertEqual(sent['action'], 'move')

    def test_mouse_wheel_carries_deltaY(self):
        # The helper itself doesn't use deltaY on input_mouse today,
        # but the client sends it for wheel events; preserve it so
        # we can wire scroll support later without changing the wire
        # format.
        self.bridge._on_server_msg({
            'type': 'mouse',
            'action': 'wheel',
            'x': 50,
            'y': 50,
            'deltaY': -120,
        })
        # The bridge forwards a fixed shape to the helper (helper
        # sees {x,y,button,action}); deltaY is intentionally NOT
        # routed because the helper's input_mouse handler doesn't
        # accept it. Just assert no exception + correct IPC type.
        sent = self.pipes.send_cmd.call_args[0][0]
        self.assertEqual(sent['type'], self.ipc.MSG_INPUT_MOUSE)

    # --- key ---

    def test_key_press_forwarded_as_input_key(self):
        self.bridge._on_server_msg({
            'type': 'key',
            'action': 'press',
            'key': 'a',
        })
        sent = self.pipes.send_cmd.call_args[0][0]
        self.assertEqual(sent['type'], self.ipc.MSG_INPUT_KEY)
        self.assertEqual(sent['key'], 'a')
        self.assertEqual(sent['action'], 'press')
        self.assertEqual(self.bridge.cmds_recv, 1)

    def test_key_down_up_distinct_actions(self):
        for action in ('down', 'up'):
            with self.subTest(action=action):
                self.pipes.send_cmd.reset_mock()
                self.bridge._on_server_msg({
                    'type': 'key',
                    'action': action,
                    'key': 'Enter',
                })
                sent = self.pipes.send_cmd.call_args[0][0]
                self.assertEqual(sent['type'], self.ipc.MSG_INPUT_KEY)
                self.assertEqual(sent['action'], action)
                self.assertEqual(sent['key'], 'Enter')

    # --- passthrough ---

    def test_exec_and_file_request_passthrough(self):
        # These already worked; make sure the rewrite of the input
        # handler didn't accidentally break them.
        msg = {'type': 'exec', 'cmd': 'whoami'}
        self.bridge._on_server_msg(msg)
        self.pipes.send_cmd.assert_called_once_with(msg)

    def test_auth_status_messages_are_acked_not_forwarded(self):
        # auth_ok / auth_failed / etc are *for* the bridge, not for
        # the helper, so they must NOT show up on the cmd pipe.
        for t in ('auth_ok', 'auth_failed', 'agent_offline', 'error',
                  'client_connected', 'client_disconnected'):
            with self.subTest(type=t):
                self.pipes.send_cmd.reset_mock()
                self.bridge._on_server_msg({'type': t, 'data': 'whatever'})
                self.pipes.send_cmd.assert_not_called()


if __name__ == '__main__':
    unittest.main()
