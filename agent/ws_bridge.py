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
import queue
import socket
import ssl
import struct
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from . import protocol as ipc

log = logging.getLogger('ws-bridge')


# Daemon threads silently die on uncaught exceptions. We use a
# module-level excepthook so any future regression in _ws_loop /
# _keepalive_loop / _frame_pump / _heartbeat shows up in the log
# with a full traceback instead of vanishing.
def _thread_excepthook(args):
    try:
        log.error(
            f'Daemon thread {args.thread.name!r} died with unhandled '
            f'exception ({type(args.exc_type).__name__}: {args.exc_value}); '
            f'WS bridge will likely be stuck until service restart',
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    except Exception:
        # excepthook must never raise
        pass
threading.excepthook = _thread_excepthook

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
        # Outgoing message queue. frame_pump calls _send() many times
        # per second; if the server stalls (no client connected, slow
        # network, full TCP send buffer) the underlying ws.send() can
        # block for seconds, which in turn blocks frame_pump -- which
        # in turn stops draining the frame queue, which makes the
        # helper's frame_sender thread fill the frame pipe and start
        # getting ERROR_NO_DATA (232) on WriteFile. The fix is to
        # make _send() non-blocking (enqueue) and let the _ws_loop
        # main loop flush the queue between recv() polls. That way
        # send back-pressure only stalls the WS reader (which has
        # nothing to do during a server stall anyway) and never
        # reaches frame_pump.
        self._outgoing_q: queue.Queue = queue.Queue(maxsize=512)
        self._outgoing_drops: int = 0
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
        # Highest input message seq we have actually processed
        # (mouse/key/exec/...). Server compares to its own counter
        # every 5s -- a growing gap means the outbound direction is
        # half-dead and we should close + reconnect.
        self._last_input_seq: int = 0
        # Reconnect bookkeeping
        self._reconnect_attempt: int = 0
        self._last_connected_at: float = 0.0
        # Half-dead WS detection. We used to be "log + continue on
        # any keepalive failure" but that meant a half-dead WS
        # (server still sends keepalive_ack but agent->server frames
        # all fail) goes undetected for hours: the agent's frame_pump
        # silently logs WinError 10054 every second while server sees
        # no traffic. Now we count consecutive failures: 1-2 are
        # probably network jitter (preserve coordinate-mapping, do
        # not reset), 3+ in a row means WS is half-dead and we force
        # a close so the outer _ws_loop reconnects. Reset to 0 on
        # any successful probe.
        self._consecutive_keepalive_failures: int = 0
        # Cross-thread reconnect signal: _keepalive_loop sets this
        # on a hard failure, _connect()'s inner recv-loop polls it
        # every iteration so we can break out *without* depending on
        # ``self._ws.close()`` to interrupt a 3600s blocking recv().
        # ``close()`` is unreliable for waking a recv() in
        # websocket-client on Windows (it just sets a flag, the
        # socket isn't actually torn down until recv()'s own timeout
        # fires). The event is the canonical signal; the settimeout
        # + close in _on_keepalive_failure is just a hint to speed
        # it up.
        self._force_reconnect_event: threading.Event = threading.Event()
        # Single-thread main loop tuning. _run_main_loop() polls
        # recv() with a short timeout so it can also drive the
        # keepalive tick on the same thread (this is the whole
        # reason we merged _keepalive_loop into _ws_loop). 0.5s is
        # the wakeup cadence: not so short that idle CPU burns, not
        # so long that a forced reconnect feels laggy.
        self._recv_poll_timeout: float = 0.5
        self._keepalive_interval: float = 25.0
        self._keepalive_ack_timeout: float = 5.0
        self._keepalive_seq: int = 0
        # _on_server_msg sets _keepalive_ack_seq[0] to the seq of
        # the keepalive_ack it just processed. _run_main_loop reads
        # this to know the pending probe succeeded. Single-element
        # list so we can mutate it from _on_server_msg without a
        # lock; both writers and readers are on the same thread.
        self._keepalive_ack_seq: list = [0]
        # The 25s cadence server ping is also tracked in
        # _keepalive_ack (a threading.Event) so future
        # code that runs in a different thread can still
        # observe probe completion. Not used by the main loop
        # anymore but kept for backward-compat with any caller
        # (e.g. tests) that wakes on it.
        self._keepalive_ack: threading.Event = threading.Event()
        # Stats
        self.frames_sent = 0
        self.cmds_recv = 0
        self.bytes_sent = 0
        self.last_error: Optional[str] = None

    # ---- public API ----

    def start(self) -> None:
        """Start all bridge threads."""
        # Three threads (was four before the keepalive merge):
        #   _ws_loop       - connect + recv + keepalive tick (single thread;
        #                    keepalive used to be a separate thread that
        #                    raced with the recv loop on `self._ws`)
        #   _frame_pump    - helper pipe -> WS
        #   _heartbeat     - 30s stats log
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
        """Maintain a persistent WS connection with reconnect.

        Single-threaded: this thread owns the WS recv() loop AND the
        keepalive tick. Combining them removes the cross-thread race
        on ``self._ws`` that made the old design fragile (keepalive
        closing the socket from one thread while _connect() was
        blocking on recv() in another; the close was unreliable at
        waking the recv on Windows, so the bridge could sit dead for
        hours).

        Trade-off: recv() now uses a short timeout (``_recv_poll_timeout``,
        default 0.5s) so the keepalive tick can run every iteration.
        That's ~2 wakeups/sec when idle, which is fine on a desktop
        service.
        """
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect()
                backoff = 1.0
                self._reconnect_attempt = 0
                # _connect blocks until disconnect; the inner recv
                # loop lives in _run_main_loop() now.
                self._run_main_loop()
            except Exception as e:
                self.last_error = repr(e)
                self._connected.clear()
                self.ws_state = 'off'
                self.auth_ok = False
                self._reconnect_attempt += 1
                # Clear the force-reconnect signal now that we've
                # acted on it. _run_main_loop leaves it set when it
                # raises so a test (or any external observer) can
                # still see why the disconnect happened; we own the
                # cleanup here.
                self._force_reconnect_event.clear()
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
            # Short recv timeout: _run_main_loop() polls recv() in a
            # loop so the keepalive tick can run on the same thread
            # (see _ws_loop docstring for why we merged the threads).
            # 0.5s strikes a balance: not so short that we burn CPU
            # on idle, not so long that force-reconnect feels laggy.
            # The server sends WS protocol pings every ~25s, which
            # websocket-client handles internally without surfacing
            # to recv(), so the short timeout is safe.
            self._ws.settimeout(self._recv_poll_timeout)
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
        # The actual recv/keepalive loop moved to _run_main_loop()
        # so this thread does not need to share `self._ws` with a
        # separate keepalive thread.

    def _run_main_loop(self) -> None:
        """Single-threaded recv + keepalive tick loop.

        Runs in the same thread as _ws_loop, after _connect() has
        finished the handshake. Exits by raising if the WS dies or
        force-reconnect is requested, which falls back into the
        outer _ws_loop reconnect branch.

        Structure: short-timeout recv() poll, then a keepalive tick.
        The short timeout is the *only* way we yield to the
        keepalive scheduler; the alternative (a second thread) is
        what got us into the cross-thread race we just deleted.
        """
        last_keepalive_send = 0.0
        pending = None  # (seq, sent_at) tuple or None

        while not self._stop.is_set() and not self._force_reconnect_event.is_set():
            # 0. Flush any pending outgoing messages. This is what
            #    keeps _send() non-blocking for frame_pump: even if
            #    the WS write takes seconds (server stall, no
            #    client, slow network), only THIS thread stalls, and
            #    only the next 0.5s recv poll is delayed.
            self._flush_outgoing_q()

            # 1. Poll recv. WebSocketTimeoutException is expected
            #    (0.5s of no business messages); keep waiting.
            try:
                raw = self._ws.recv()
                if not raw:
                    raise ConnectionError('server closed')
                self._handle_business_msg(raw)
            except WebSocketTimeoutException:
                # Idle. Drive the keepalive tick below.
                pass
            except Exception as e:
                log.warning(f'WS recv error: {e}')
                raise

            # 2. Drive keepalive. Two phases: send a fresh probe
            #    when the interval has elapsed, otherwise check the
            #    pending probe for an ack or timeout.
            now = time.time()
            if pending is None:
                if now - last_keepalive_send >= self._keepalive_interval:
                    seq = self._next_keepalive_seq()
                    self._send({'type': 'keepalive', 'ts': now, 'seq': seq})
                    pending = (seq, now)
                    last_keepalive_send = now
            else:
                seq, sent_at = pending
                # Did the ack arrive (was set in _on_server_msg)?
                if self._keepalive_ack_seq[0] >= seq:
                    self._consecutive_keepalive_failures = 0
                    self._keepalive_ack.clear()
                    pending = None
                    continue
                # Hard timeout: did the ack window expire?
                if now - sent_at > self._keepalive_ack_timeout:
                    self._on_keepalive_failure(
                        f'keepalive #{seq}: no ack in '
                        f'{self._keepalive_ack_timeout:.1f}s '
                        f'(server->agent direction is half-dead)'
                    )
                    pending = None
                    if self._force_reconnect_event.is_set():
                        # _on_keepalive_failure already set the event
                        # at failure 3/3; the next while-iteration
                        # check will exit.
                        pass

        if self._force_reconnect_event.is_set():
            # Don't clear here -- the outer _ws_loop's except branch
            # clears it after logging the disconnect reason. Keeping
            # it set until then means a test that catches the
            # ConnectionError can still assert is_set() is True and
            # know the force-reconnect was the cause.
            raise ConnectionError('force-reconnect requested by keepalive (WS half-dead)')

    def _handle_business_msg(self, raw: str) -> None:
        """Decode + dispatch one business message from the server.

        Pulled out of the recv() inner loop so _run_main_loop() can
        stay short and so test code can drive it directly with a
        JSON string. The keepalive_ack_seq[0] write here is what
        _run_main_loop's keepalive tick reads to know the ack came
        back; both happen on the same thread, so the single-element
        list trick needs no lock.
        """
        msg = json.loads(raw)
        if msg.get('type') == 'auth_ok' and not self.auth_ok:
            self.auth_ok = True
            self.ws_state = 'authed'
            log.info(f'WS auth_ok: agent_id={msg.get("agentId")} ready for remote clients')
        try:
            self._on_server_msg(msg)
        except Exception as e:
            log.warning(f"WS->helper msg handler error: {e}", exc_info=True)

    def _next_keepalive_seq(self) -> int:
        """Bump and return the next keepalive sequence number."""
        self._keepalive_seq += 1
        return self._keepalive_seq

    def _on_keepalive_failure(self, reason: str) -> None:
        """Record a keepalive probe failure; force reconnect at 3/3.

        Replaces the old _keepalive_loop's failure branch. Called by
        _run_main_loop when a pending keepalive's ack window
        expires. Side effects:
          - increments _consecutive_keepalive_failures
          - logs the failure with the current /3 count
          - at 3/3, sets _force_reconnect_event (so _run_main_loop
            exits), resets the counter, and best-effort closes the
            socket to short-circuit any in-flight recv().
        """
        self._consecutive_keepalive_failures += 1
        if self._consecutive_keepalive_failures >= 3:
            # 3 consecutive keepalive failures in a row
            # (~75-90s wall time) means the WS is half-dead: the
            # server can still send us keepalive_acks (or we are not
            # detecting the ack in time), but our own outbound
            # direction is broken -- evidenced by frame_pump
            # logging WinError 10054 every second. Force a close so
            # the next recv() in _run_main_loop raises
            # ConnectionClosed and the outer _ws_loop enters its
            # reconnect branch. The cost is a brief App-side
            # coordinate remapping (HELLO/screen_size
            # re-negotiation), which is much cheaper than 12 hours
            # of silent "agent online but not actually doing
            # anything".
            log.error(
                f'WS keepalive probe failed {self._consecutive_keepalive_failures} '
                f'times in a row; forcing reconnect (WS half-dead): {reason}'
            )
            self._consecutive_keepalive_failures = 0
            self._keepalive_ack.clear()
            # The event is the *guaranteed* wake for _run_main_loop:
            # the next while-iteration check exits the loop. The
            # settimeout + close is just a latency optimization so
            # any recv() that's currently blocked wakes up quickly
            # (websocket-client's close() doesn't reliably interrupt
            # a blocking recv on Windows).
            self._force_reconnect_event.set()
            try:
                if self._ws is not None:
                    try:
                        self._ws.settimeout(0.1)
                    except Exception:
                        pass
                    self._ws.close()
            except Exception as close_err:
                # Best effort: even if close() raises we still want
                # to fall through and let the next _run_main_loop
                # poll see the force-reconnect event.
                log.warning(f'WS force-close raised: {close_err}')
        else:
            # 1 or 2 consecutive failures -- most likely network
            # jitter, not a half-dead WS. Log loudly with a "/3"
            # counter so operators see we are N probes from a forced
            # reconnect. The pending keepalive was already cleared
            # by the caller; we just clear the ack event so the next
            # probe starts clean.
            log.warning(
                f'WS keepalive probe failed '
                f'({self._consecutive_keepalive_failures}/3, will force '
                f'reconnect at 3): {reason}'
            )
            self._keepalive_ack.clear()


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
        if t == 'keepalive_ack':
            # Round-trip response from server. _keepalive_loop is
            # blocked on this Event. Wake it up so it can check the
            # seq matches the one it just sent.
            seq = msg.get('seq', 0)
            self._keepalive_ack_seq[0] = max(self._keepalive_ack_seq[0], seq)
            self._keepalive_ack.set()
            return
        if t == 'mouse':
            # mouse event from remote client (action: down/up/move/click/double_click/wheel)
            self.cmds_recv += 1
            # Record the highest input seq we have actually processed
            # for the input_ack feedback loop. Server uses the gap
            # (sent - acked) to detect a server->agent half-close
            # within 5s instead of waiting for the keepalive probe
            # to time out.
            if 'seq' in msg:
                seq_val = msg.get("seq", 0)
                self._last_input_seq = max(self._last_input_seq, seq_val)
            try:
                cmd = {
                    'type': ipc.MSG_INPUT_MOUSE,
                    'x': msg.get('x'),
                    'y': msg.get('y'),
                    'button': msg.get('button', 'left'),
                    'action': msg.get('action', 'move'),
                }
                self.pipes.send_cmd(cmd)
                self.cmds_sent += 1
                log.info(f'WS->helper mouse {cmd["action"]} ({cmd["x"]},{cmd["y"]}) {cmd["button"]}')
            except Exception as e:
                log.warning(f'WS->helper mouse forward failed: {e}')
            return
        if t == 'key':
            # keyboard event from remote client (action: down/up/press)
            self.cmds_recv += 1
            if 'seq' in msg:
                seq_val = msg.get("seq", 0)
                self._last_input_seq = max(self._last_input_seq, seq_val)
            try:
                cmd = {
                    'type': ipc.MSG_INPUT_KEY,
                    'key': msg.get('key', ''),
                    'action': msg.get('action', 'press'),
                }
                self.pipes.send_cmd(cmd)
                self.cmds_sent += 1
                log.info(f'WS->helper key {cmd["action"]} "{cmd["key"]}"')
            except Exception as e:
                log.warning(f'WS->helper key forward failed: {e}')
            return
        if t in ('exec', 'file_request'):
            # Server-relayed command; forward to helper
            self.cmds_recv += 1
            try:
                self.pipes.send_cmd(msg)
                self.cmds_sent += 1
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
        """Enqueue a message for the WS writer.

        Non-blocking: if the outgoing queue is full (server is
        stalled / no client / slow network), drop and log a warning
        rather than block the caller (typically frame_pump). The
        actual TCP/WS write is performed by _flush_outgoing_q()
        inside the _ws_loop main loop.

        The 512-slot queue is enough for ~30s of 60fps screen
        captures even at a high data rate; in practice it stays
        near-empty because _ws_loop drains it on every iteration
        (the 0.5s recv poll returns between frames).
        """
        try:
            self._outgoing_q.put_nowait(msg)
        except queue.Full:
            self._outgoing_drops += 1
            if self._outgoing_drops % 100 == 1:
                # Throttle: don't spam the log on sustained stalls.
                log.warning(
                    f'outgoing_q full, dropped msg type={msg.get("type")!r} '
                    f'(total drops: {self._outgoing_drops})'
                )

    def _flush_outgoing_q(self) -> None:
        """Drain the outgoing queue, sending each message via WS.

        Called by _ws_loop between recv() polls so send back-pressure
        only stalls the WS reader (which has nothing to do during a
        server stall anyway) and never reaches frame_pump.

        We bound each flush to a small batch so a single slow
        ws.send() doesn't starve recv() entirely; the next poll
        picks up the rest.
        """
        # Bounded batch: at most 64 messages per flush. The next
        # _run_main_loop iteration (within 0.5s) handles the rest.
        for _ in range(64):
            try:
                msg = self._outgoing_q.get_nowait()
            except queue.Empty:
                return
            try:
                data = json.dumps(msg, ensure_ascii=False)
                self._ws.send(data)
            except Exception as e:
                # Don't try to recover here; the recv() side will
                # notice the dead socket via the next poll / keepalive
                # and reconnect. We do NOT re-enqueue -- that would
                # re-send stale frames after a reconnect.
                log.warning(f'WS send failed in flush: {e}')
                # Drop the rest of the queue too -- if ws.send
                # raised, the socket is probably dead and the outer
                # _ws_loop will reconnect. Holding the messages would
                # just make them stale.
                try:
                    while True:
                        self._outgoing_q.get_nowait()
                except queue.Empty:
                    pass
                return


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
