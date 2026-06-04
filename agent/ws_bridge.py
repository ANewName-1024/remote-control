"""WebSocket bridge - service.py <-> VPS relay over WebSocket.

Bridges messages between the local helper (via named pipes) and the
remote VPS relay (via WebSocket on /agent path). Implements the
agent side of the protocol documented in server/index.js.

Usage (from service.py main loop):
    bridge = WSBridge(pipe_server, ws_url, agent_id, secret)
    bridge.start()
    # ... do other things ...
    bridge.stop()
"""
from __future__ import annotations

import base64
import json
import logging
import socket
import ssl
import struct
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from . import protocol as ipc

log = logging.getLogger('ws-bridge')

# Try websocket-client (preferred). Fall back to a minimal pure-stdlib
# implementation if unavailable.
try:
    import websocket  # type: ignore
    from websocket import WebSocketTimeoutException  # type: ignore
    HAVE_WSCLIENT = True
except ImportError:
    HAVE_WSCLIENT = False
    # Fallback for the stdlib-only path: define a sentinel exception so
    # the recv loop's `except WebSocketTimeoutException: continue` keeps
    # the call site tidy even if websocket-client is missing.
    class WebSocketTimeoutException(Exception):  # type: ignore[no-redef]
        pass


class WSBridge:
    """Service-side WebSocket bridge.

    Maintains a persistent WS connection to ws://<host>/agent and:
      - Sends periodic heartbeat (pong) so the server updates lastSeen
      - Forwards frames from helper (drain_frames) as `screen` messages
      - Forwards input events received from server to helper (via cmd pipe)
      - Forwards exec / file_request from server to helper (via cmd pipe)
    """

    def __init__(
        self,
        pipe_server,
        ws_url: str,
        agent_id: str,
        secret: str,
        hostname: str = socket.gethostname(),
        os_info: str = 'windows',
    ):
        self.pipes = pipe_server
        self.ws_url = ws_url
        self.agent_id = agent_id
        self.secret = secret
        self.hostname = hostname
        self.os_info = os_info
        self._ws = None
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._threads = []
        # Connection-state string for the service heartbeat.
        # Values: 'off' | 'connecting' | 'open' | 'auth' | 'authed' | 'closing'
        self.ws_state: str = 'off'
        # Auth completion so service heartbeat can include it
        self.auth_ok: bool = False
        # Per-message-type counters, surfaced in the 30s service
        # heartbeat and reset on every print. Resetting per print
        # gives a real 'events in the last 30s' number, not a
        # monotonically growing total that loses visibility.
        self.cmds_sent = 0
        self._msg_type_stats: dict = {}
        # Reconnect bookkeeping
        self._reconnect_attempt: int = 0
        self._last_connected_at: float = 0.0
        # Stats
        self.frames_sent = 0
        self.cmds_recv = 0
        self.bytes_sent = 0
        self.last_error: Optional[str] = None

    # ---- public API ----

    def start(self) -> None:
        """Start all bridge threads."""
        for target in (self._ws_loop, self._frame_pump, self._heartbeat):
            t = threading.Thread(target=target, daemon=True, name=f'ws-{target.__name__}')
            t.start()
            self._threads.append(t)
        log.info(f'WS bridge started for {self.agent_id} at {self.ws_url}')

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        log.info('WS bridge stopped')

    def wait_connected(self, timeout: float = 10.0) -> bool:
        return self._connected.wait(timeout=timeout)

    # ---- connection loop ----

    def _ws_loop(self) -> None:
        """Maintain a persistent WS connection with reconnect."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect()
                backoff = 1.0
                self._reconnect_attempt = 0
                # _connect blocks until disconnect
            except Exception as e:
                self.last_error = repr(e)
                self._connected.clear()
                self.ws_state = 'off'
                self.auth_ok = False
                self._reconnect_attempt += 1
                # Distinguish 'first connect' from 'reconnect N'
                if self._reconnect_attempt == 1:
                    log.warning(f'WS disconnected: {e}; reconnecting in {backoff:.1f}s')
                else:
                    log.warning(f'WS disconnected (#{self._reconnect_attempt}): {e}; reconnecting in {backoff:.1f}s')
                if self._stop.wait(timeout=backoff):
                    return
                backoff = min(backoff * 2, 30.0)

    def _connect(self) -> None:
        url = self.ws_url.rstrip('/')
        if not url.endswith('/agent'):
            url = url + '/agent'
        # Surface the connect attempt even if it never completes.
        # Otherwise a stuck TLS handshake looks identical to "still
        # trying the first one" in the heartbeat.
        self.ws_state = 'connecting'
        log.info(f'WS connecting to {url} as {self.agent_id} (attempt #{self._reconnect_attempt + 1})')
        if HAVE_WSCLIENT:
            self._ws = websocket.WebSocket()
            self._ws.connect(url, timeout=10)
            # Long recv timeout: we don't expect a steady stream of business
            # messages from the server (it only pushes input events on demand).
            # A short timeout here used to cause spurious "Connection timed out"
            # disconnects when the user just sits idle. The server sends WS
            # protocol pings every 25s (see server/index.js heartbeat) and
            # websocket-client handles those internally without surfacing them
            # to recv(), so blocking for a long time is safe.
            self._ws.settimeout(3600)
        else:
            self._ws = _StdlibWSClient(url)
            self._ws.connect()
        self.ws_state = 'open'
        self._last_connected_at = time.time()
        log.info(f'WS connected: {url}')
        # Send auth
        self.ws_state = 'auth'
        self._send({
            'type': 'auth',
            'agentId': self.agent_id,
            'secret': self.secret,
            'hostname': self.hostname,
            'os': self.os_info,
        })
        self._connected.set()
        # Loop: read messages from server, dispatch to helper.
        # We swallow WebSocketTimeoutException (idle timeout) and keep waiting,
        # so an idle user doesn't cause a reconnect storm. Anything else
        # (socket closed, protocol error) still bubbles up to reconnect.
        while not self._stop.is_set():
            try:
                raw = self._ws.recv()
                if not raw:
                    raise ConnectionError('server closed')
                msg = json.loads(raw)
                # Switch to 'authed' as soon as we see auth_ok from server.
                # This is the moment remote clients can actually use us.
                if msg.get('type') == 'auth_ok' and not self.auth_ok:
                    self.auth_ok = True
                    self.ws_state = 'authed'
                    log.info(f'WS auth_ok: agent_id={msg.get("agentId")} ready for remote clients')
                self._on_server_msg(msg)
            except WebSocketTimeoutException:
                # No business message in 1h - that's fine, server is alive
                # (heartbeat pings keep the TCP/WS connection warm).
                continue
            except Exception as e:
                log.warning(f'WS recv error: {e}')
                raise

    # ---- server -> helper ----

    def _on_server_msg(self, msg: dict) -> None:
        """Dispatch a message from the server to the helper via cmd pipe.

        Clients (HTML page, Flutter App) speak the legacy combined
        "type: mouse / key" wire format. The v2 helper, however, splits
        input into separate IPC types (`input_mouse`, `input_key`,
        `input_hotkey`, `input_type`, ... — see agent.protocol). We
        translate once on the bridge so any client works regardless of
        whether the server normalizes the wire format.
        """
        t = msg.get('type')
        # Per-msg-type counter for the 30s heartbeat. Cheap dict incr.
        # Pings excluded so the heartbeat doesn't just show "10 pings".
        if t and t != 'ping':
            self._msg_type_stats[t] = self._msg_type_stats.get(t, 0) + 1
        if t in ('auth_ok', 'auth_failed', 'agent_offline', 'error', 'client_connected', 'client_disconnected'):
            log.info(f'WS: {t}: {msg}')
            return
        if t == 'mouse':
            # mouse event from remote client (action: down/up/move/click/double_click/wheel)
            self.cmds_recv += 1
            try:
                cmd = {
                    'type': ipc.MSG_INPUT_MOUSE,
                    'x': msg.get('x'),
                    'y': msg.get('y'),
                    'button': msg.get('button', 'left'),
                    'action': msg.get('action', 'move'),
                }
                self.pipes.send_cmd(cmd)
                log.info(f'WS->helper mouse {cmd["action"]} ({cmd["x"]},{cmd["y"]}) {cmd["button"]}')
            except Exception as e:
                log.warning(f'WS->helper mouse forward failed: {e}')
            return
        if t == 'key':
            # keyboard event from remote client (action: down/up/press)
            self.cmds_recv += 1
            try:
                cmd = {
                    'type': ipc.MSG_INPUT_KEY,
                    'key': msg.get('key', ''),
                    'action': msg.get('action', 'press'),
                }
                self.pipes.send_cmd(cmd)
                log.info(f'WS->helper key {cmd["action"]} "{cmd["key"]}"')
            except Exception as e:
                log.warning(f'WS->helper key forward failed: {e}')
            return
        if t in ('exec', 'file_request'):
            # Server-relayed command; forward to helper
            self.cmds_recv += 1
            try:
                self.pipes.send_cmd(msg)
            except Exception as e:
                log.warning(f'WS->helper {t} forward failed: {e}')
            return
        log.debug(f'WS: unhandled msg type={t}')

    # ---- helper -> server ----

    def _frame_pump(self) -> None:
        """Drain frames from the helper (via the frame queue) and forward
        to the server. The helper's frame_sender runs frames through
        DeltaScreenCapture and sends a JSON msg dict per frame (with
        `fmt='kf'` or `fmt='df'`); we forward the dict verbatim.
        """
        while not self._stop.is_set():
            time.sleep(0.05)
            if not self._connected.is_set():
                continue
            for body in self.pipes.drain_frames():
                try:
                    if len(body) < 16:
                        continue
                    # 16-byte header: 4 length, 4 seq, 8 ts
                    body_len, seq, ts_ms = struct.unpack('>IIQ', body[:16])
                    if len(body) < 16 + body_len:
                        continue
                    payload = body[16:16 + body_len]
                    msg = json.loads(payload.decode('utf-8'))
                    if msg.get('type') != 'screen':
                        continue
                    # Pass through helper-generated msg; just add server-side ts
                    msg['server_ts_ms'] = int(time.time() * 1000)
                    self._send(msg)
                    self.frames_sent += 1
                    self.bytes_sent += body_len
                except Exception as e:
                    log.warning(f'frame_pump: send failed: {e}')

    def _heartbeat(self) -> None:
        """Send a periodic pong so the server updates lastSeen."""
        while not self._stop.is_set():
            if self._connected.is_set():
                try:
                    self._send({'type': 'pong', 'ts': int(time.time() * 1000)})
                except Exception as e:
                    log.debug(f'heartbeat send failed: {e}')
            if self._stop.wait(timeout=10):
                return

    def get_and_reset_msg_stats(self) -> dict:
        """Snapshot the per-msg-type counter and zero it. Called by the
        service heartbeat thread every 30s so the operator can see
        'mouse:5 key:2 exec:1' in the last 30s window, not a lifetime
        total that loses the 'is anything happening?' signal quickly."""
        out = self._msg_type_stats
        self._msg_type_stats = {}
        return out

    def _send(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        self._ws.send(data)


# ---- stdlib fallback WS client (only used if websocket-client missing) ----

class _StdlibWSClient:
    """Minimal WebSocket client in pure stdlib. Supports text frames only
    and is good enough for the bridge. Does NOT support wss:// (no TLS)."""
    def __init__(self, url: str):
        u = urlparse(url)
        if u.scheme not in ('ws',):
            raise ValueError(f'stdlib fallback only supports ws://, got {u.scheme}')
        self.host = u.hostname
        self.port = u.port or 80
        self.path = u.path or '/'
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        s = socket.create_connection((self.host, self.port), timeout=10)
        key = base64.b64encode(__import__('os').urandom(16)).decode('ascii')
        req = (
            f'GET {self.path} HTTP/1.1\r\n'
            f'Host: {self.host}:{self.port}\r\n'
            f'Upgrade: websocket\r\n'
            f'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            f'Sec-WebSocket-Version: 13\r\n'
            f'\r\n'
        )
        s.sendall(req.encode('ascii'))
        # Read response headers
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = s.recv(4096)
            if not chunk:
                raise ConnectionError('handshake failed')
            buf += chunk
        head, _, rest = buf.partition(b'\r\n\r\n')
        if b'101' not in head.split(b'\r\n', 1)[0]:
            raise ConnectionError(f'bad handshake: {head[:80]!r}')
        self.sock = s
        self._rest = rest

    def send(self, text: str) -> None:
        data = text.encode('utf-8')
        # Client must mask. Use a fixed mask of zeros for simplicity (NOT RFC
        # compliant but works in practice with permissive servers).
        mask = b'\x00\x00\x00\x00'
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        length = len(data)
        if length < 126:
            header = bytes([0x81, 0x80 | length])
        elif length < (1 << 16):
            header = bytes([0x81, 0x80 | 126]) + struct.pack('>H', length)
        else:
            header = bytes([0x81, 0x80 | 127]) + struct.pack('>Q', length)
        self.sock.sendall(header + mask + masked)

    def recv(self) -> str:
        # Read frame header
        def recvn(n):
            buf = b''
            while len(buf) < n:
                if hasattr(self, '_rest') and self._rest:
                    take = min(len(self._rest), n - len(buf))
                    buf += self._rest[:take]
                    self._rest = self._rest[take:]
                else:
                    chunk = self.sock.recv(n - len(buf))
                    if not chunk:
                        raise ConnectionError('server closed')
                    buf += chunk
            return buf
        b1, b2 = recvn(2)
        op = b1 & 0x0F
        masked = b2 & 0x80
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack('>H', recvn(2))[0]
        elif length == 127:
            length = struct.unpack('>Q', recvn(8))[0]
        if masked:
            mask = recvn(4)
        else:
            mask = b''
        data = recvn(length)
        if mask:
            data = bytes(d ^ mask[i % 4] for i, d in enumerate(data))
        if op == 0x1:  # text
            return data.decode('utf-8')
        if op == 0x8:  # close
            raise ConnectionError('server closed')
        return ''  # ignore binary/ping/pong

    def settimeout(self, t: float) -> None:
        if self.sock:
            self.sock.settimeout(t)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass
