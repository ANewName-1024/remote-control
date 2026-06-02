"""Service process - runs as SYSTEM in Session 0.

Responsibilities:
  - Spawn the helper process in the active user session (Session 1+)
  - Maintain two named pipes: cmd (bidirectional JSON) and frame (helper -> service)
  - Forward frames from helper to WebSocket (with delta encoding)
  - Forward input events from WebSocket to helper
  - All other agent behavior (file transfer, exec, system tray, etc.)

Architecture:
  +-------------+   named pipes   +---------+   WebSocket   +--------+
  |   helper    | <-------------> | service | <-----------> | relay  |
  | (user sess) |  frames + cmd   | (sess 0)|   auth + IO   | (VPS)  |
  +-------------+                 +---------+               +--------+

The service and helper are typically the same Python entry point,
selected by --mode=service vs --mode=helper.
"""
import os
import sys
import time
import json
import ctypes
import secrets
import logging
import platform
import socket
import threading
import subprocess
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from agent import protocol as ipc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [service %(levelname)s] %(message)s',
)
log = logging.getLogger('service')

# Auth token: passed to helper via env var. Prevents random local
# processes from injecting commands into the named pipe.
AUTH_TOKEN = secrets.token_hex(ipc.AUTH_TOKEN_LENGTH)

# ---- Win32 helpers --------------------------------------------------------

user32  = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
wtsapi32 = ctypes.windll.wtsapi32
advapi32 = ctypes.windll.advapi32

# Constants
WTS_CURRENT_SERVER_HANDLE = ctypes.c_void_p(0)
TOKEN_ALL_ACCESS = 0x000F01FF
TOKEN_QUERY       = 0x0008
TOKEN_DUPLICATE   = 0x0002
TOKEN_ASSIGN_PRIMARY = 0x0001
SecurityImpersonation = 2
TokenPrimary       = 1
CREATE_NEW_CONSOLE = 0x00000010
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0

WTSQueryUserToken = wtsapi32.WTSQueryUserToken
WTSQueryUserToken.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
WTSQueryUserToken.restype  = ctypes.c_bool

WTSFreeMemory = wtsapi32.WTSFreeMemory
WTSFreeMemory.argtypes = [ctypes.c_void_p]
WTSFreeMemory.restype  = None

WTSGetActiveConsoleSessionId = kernel32.WTSGetActiveConsoleSessionId
WTSGetActiveConsoleSessionId.argtypes = []
WTSGetActiveConsoleSessionId.restype  = ctypes.c_uint


def get_active_console_session_id() -> int:
    """Return the Session ID of the user currently logged in to the physical
    console. Returns 0xFFFFFFFF if none (e.g. Session 0 only)."""
    return WTSGetActiveConsoleSessionId() or 0


def get_user_token(session_id: int):
    """Get an impersonation token for the user logged into `session_id`.
    Returns the token handle, or None on failure."""
    token = ctypes.c_void_p()
    ok = WTSQueryUserToken(session_id, ctypes.byref(token))
    if not ok:
        err = ctypes.get_last_error()
        log.warning(f'WTSQueryUserToken({session_id}) failed: winerror={err}')
        return None
    return token.value


def spawn_helper_in_user_session() -> Optional[subprocess.Popen]:
    """Spawn the helper process in the active user session.

    Used when the service runs as SYSTEM. We:
      1. Find the active console session
      2. WTSQueryUserToken to get the user's token
      3. Duplicate as a primary token
      4. CreateProcessAsUser with lpDesktop='Default'
    """
    session_id = get_active_console_session_id()
    if session_id == 0 or session_id == 0xFFFFFFFF:
        log.warning(f'no active console session (id={session_id}); helper not spawned')
        return None

    user_token = get_user_token(session_id)
    if not user_token:
        return None

    # Duplicate token as primary
    DuplicateTokenEx = advapi32.DuplicateTokenEx
    DuplicateTokenEx.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
    ]
    DuplicateTokenEx.restype = ctypes.c_bool
    new_token = ctypes.c_void_p()
    ok = DuplicateTokenEx(
        user_token,
        TOKEN_ALL_ACCESS,
        None,
        SecurityImpersonation,
        TokenPrimary,
        ctypes.byref(new_token),
    )
    if not ok:
        log.warning(f'DuplicateTokenEx failed: err={ctypes.get_last_error()}')
        ctypes.windll.kernel32.CloseHandle(user_token)
        return None
    kernel32.CloseHandle(user_token)
    primary_token = new_token.value

    # Build command line
    python = sys.executable
    script = os.path.join(_HERE, '..', 'agent')  # the agent package
    # We use the package entry point so the dispatcher picks up --mode=helper
    cmd = [python, '-m', 'agent', '--mode=helper']

    # Environment: pass the auth token so the helper can authenticate
    env = os.environ.copy()
    env['RC_HELPER_TOKEN'] = AUTH_TOKEN
    env['RC_MODE'] = 'helper'
    env['PYTHONIOENCODING'] = 'utf-8'

    # Build the environment block (CreateProcessAsUser wants a double-NUL-terminated block)
    env_block = '\0'.join(f'{k}={v}' for k, v in env.items()) + '\0\0'
    env_block_buf = ctypes.create_unicode_buffer(env_block)

    cmd_line = subprocess.list2cmdline(cmd)
    cmd_line_buf = ctypes.create_unicode_buffer(cmd_line)

    # STARTUPINFO with lpDesktop='Default' so the helper inherits the user's desktop
    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ('cb',              ctypes.c_uint32),
            ('lpReserved',      ctypes.c_wchar_p),
            ('lpDesktop',       ctypes.c_wchar_p),
            ('lpTitle',         ctypes.c_wchar_p),
            ('dwX',             ctypes.c_uint32),
            ('dwY',             ctypes.c_uint32),
            ('dwXSize',         ctypes.c_uint32),
            ('dwYSize',         ctypes.c_uint32),
            ('dwXCountChars',   ctypes.c_uint32),
            ('dwYCountChars',   ctypes.c_uint32),
            ('dwFillAttribute', ctypes.c_uint32),
            ('dwFlags',         ctypes.c_uint32),
            ('wShowWindow',     ctypes.c_uint16),
            ('cbReserved2',     ctypes.c_uint16),
            ('lpReserved2',     ctypes.c_void_p),
            ('hStdInput',       ctypes.c_void_p),
            ('hStdOutput',      ctypes.c_void_p),
            ('hStdError',       ctypes.c_void_p),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('hProcess',    ctypes.c_void_p),
            ('hThread',     ctypes.c_void_p),
            ('dwProcessId', ctypes.c_uint32),
            ('dwThreadId',  ctypes.c_uint32),
        ]

    si = STARTUPINFO()
    si.cb = ctypes.sizeof(STARTUPINFO)
    si.lpDesktop = 'Default'
    si.dwFlags = STARTF_USESHOWWINDOW
    si.wShowWindow = SW_HIDE  # hidden

    pi = PROCESS_INFORMATION()

    CreateProcessAsUserW = advapi32.CreateProcessAsUserW
    CreateProcessAsUserW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_bool, ctypes.c_uint,
        ctypes.c_void_p, ctypes.c_wchar_p,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    CreateProcessAsUserW.restype = ctypes.c_bool

    ok = CreateProcessAsUserW(
        primary_token,
        None,           # app name (None => use cmd line)
        cmd_line_buf.value,
        None, None,     # process / thread attrs
        False,          # inherit handles
        CREATE_UNICODE_ENVIRONMENT,
        env_block_buf,
        None,           # current dir
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    kernel32.CloseHandle(primary_token)
    if not ok:
        err = ctypes.get_last_error()
        log.warning(f'CreateProcessAsUserW failed: err={err}')
        return None

    log.info(f'helper spawned: pid={pi.dwProcessId} in session={session_id}')
    # Note: not waiting on the process here - we monitor via named pipe.

    # Wrap the handles in a pseudo-Popen-like object
    class _FakePopen:
        def __init__(self, hProcess, hThread, pid):
            self._hProcess = hProcess
            self._hThread = hThread
            self.pid = pid

        def poll(self):
            WAIT_OBJECT_0 = 0
            res = kernel32.WaitForSingleObject(self._hProcess, 0)
            if res == WAIT_OBJECT_0:
                exit_code = ctypes.c_uint32()
                kernel32.GetExitCodeProcess(self._hProcess, ctypes.byref(exit_code))
                return exit_code.value
            return None

        def wait(self, timeout=None):
            res = kernel32.WaitForSingleObject(self._hProcess, timeout or 0xFFFFFFFF)
            return res == 0

        def terminate(self):
            kernel32.TerminateProcess(self._hProcess, 1)

    return _FakePopen(pi.hProcess, pi.hThread, pi.dwProcessId)


# ---- Pipe server ----------------------------------------------------------

class PipeServer:
    """Accept named-pipe connections in a background thread.

    For each pipe name, run a `ConnectionHandler` coroutine.
    """

    def __init__(self):
        self.running = True
        self.threads = []
        self.cmd_conn  = None  # the most recent cmd-pipe connection
        self.frame_conn = None
        self.cmd_lock  = threading.Lock()
        self.frame_lock = threading.Lock()
        self.on_hello = None  # callback(hello_dict) when helper sends HELLO

    def _pipe_thread(self, pipe_name, accept):
        import win32pipe  # type: ignore
        import win32file  # type: ignore
        log.info(f'pipe server starting: {pipe_name}')
        while self.running:
            try:
                handle = win32pipe.CreateNamedPipe(
                    pipe_name,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    # PIPE_BYTE_STREAM mode: ReadFile(h, N) reads up to N bytes from the
                    # stream. We rely on the length-prefix framing in agent/protocol.py
                    # to delimit messages. PIPE_TYPE_MESSAGE is harder because ReadFile
                    # returns one whole message at a time regardless of N requested.
                    win32pipe.PIPE_WAIT,
                    win32pipe.PIPE_UNLIMITED_INSTANCES,  # OS multiplexes; we close the old handle per-connection
                    1024 * 1024,  # out buffer 1MB
                    1024 * 1024,  # in buffer 1MB
                    0,  # default timeout
                    None,
                )
                win32pipe.ConnectNamedPipe(handle, None)
                log.info(f'pipe connected: {pipe_name}')
                # If a previous helper is still connected, the new one will
                # block until the old one disconnects. We close the old one.
                if pipe_name == ipc.CMD_PIPE:
                    with self.cmd_lock:
                        if self.cmd_conn:
                            try: win32file.CloseHandle(self.cmd_conn)
                            except Exception: pass
                        self.cmd_conn = handle
                    accept('cmd', handle)
                else:
                    with self.frame_lock:
                        if self.frame_conn:
                            try: win32file.CloseHandle(self.frame_conn)
                            except Exception: pass
                        self.frame_conn = handle
                    accept('frame', handle)
            except Exception as e:
                log.warning(f'pipe server {pipe_name} error: {e}')
                time.sleep(0.5)

    def start(self, on_hello):
        self.on_hello = on_hello
        for name in (ipc.CMD_PIPE, ipc.FRAME_PIPE):
            t = threading.Thread(target=self._pipe_thread, args=(name, self._on_connection),
                                 name=f'pipe-{name}', daemon=True)
            t.start()
            self.threads.append(t)

    def _on_connection(self, kind, handle):
        if kind == 'cmd':
            # Run in a thread to handle messages from helper
            t = threading.Thread(target=self._cmd_session, args=(handle,),
                                 name='cmd-session', daemon=True)
            t.start()
        # frame: we just close the handle since the helper writes to it
        # and we read directly via ReadFile. But for now we treat the pipe
        # as duplex and let the frame-sender thread on the helper side
        # close it from the other end when it exits.

    def _cmd_session(self, handle):
        import win32file  # type: ignore
        try:
            while self.running:
                msg = ipc.read_msg(handle)
                if msg is None:
                    log.info('cmd pipe: helper disconnected')
                    break
                t = msg.get('type')
                if t == ipc.MSG_HELLO:
                    if msg.get('token') != AUTH_TOKEN:
                        log.warning('helper auth token mismatch; rejecting')
                        break
                    log.info(f'helper HELLO: pid={msg.get("pid")} session={msg.get("session_id")} backend={msg.get("backend")}')
                    if self.on_hello:
                        try:
                            self.on_hello(msg)
                        except Exception as e:
                            log.warning(f'on_hello callback error: {e}')
                    ipc.send_msg(handle, {'type': ipc.MSG_HELLO_ACK})
                else:
                    # Forward everything else to the app via callback
                    if self.on_hello and hasattr(self.on_hello, '__self__'):
                        # on_hello is a bound method, so we have the impl;
                        # the simpler path: the app pulls via a queue
                        pass
                    # Currently we only handle HEARTBEAT explicitly:
                    if t == ipc.MSG_HEARTBEAT:
                        log.debug('helper heartbeat')
                    elif t == ipc.MSG_BYE:
                        log.info('helper sent BYE')
                        break
                    else:
                        log.debug(f'cmd msg: {t}')
        except Exception as e:
            log.warning(f'cmd session error: {e}')
        finally:
            try: win32file.CloseHandle(handle)
            except Exception: pass
            with self.cmd_lock:
                self.cmd_conn = None

    def send_cmd(self, msg: dict) -> bool:
        """Send a message to the helper over the cmd pipe."""
        import win32file  # type: ignore
        with self.cmd_lock:
            if not self.cmd_conn:
                return False
            try:
                ipc.send_msg(self.cmd_conn, msg)
                return True
            except Exception as e:
                log.warning(f'send_cmd failed: {e}')
                return False

    def read_frame(self, timeout_ms: int = 100) -> Optional[bytes]:
        """Try to read a frame from the frame pipe. Non-blocking.

        TODO(perf): on a busy service this should be a dedicated thread
        doing a blocking ReadFile loop, not polled from the main loop.
        For now we just attempt a 1-byte read and only continue if data
        is available.
        """
        import win32file  # type: ignore
        import win32pipe  # type: ignore
        with self.frame_lock:
            if not self.frame_conn:
                return None
            try:
                avail, _, _ = win32pipe.PeekNamedPipe(self.frame_conn, 0)
            except Exception as e:
                log.debug(f'read_frame: PeekNamedPipe: {e}')
                return None
            if avail < 4:
                return None
            return ipc.read_envelope(self.frame_conn)

    def stop(self):
        self.running = False
        import win32file  # type: ignore
        for h in (self.cmd_conn, self.frame_conn):
            if h:
                try: win32file.CloseHandle(h)
                except Exception: pass


# ---- Main run() -----------------------------------------------------------

def run(config_dir: str = None):
    log.info(f'service starting (pid={os.getpid()})')
    log.info(f'auth token generated ({len(AUTH_TOKEN)} chars)')

    pipes = PipeServer()
    helper_proc = None

    def on_hello(msg):
        nonlocal helper_proc
        log.info(f'helper reported backend={msg.get("backend")} screen={msg.get("screen_w")}x{msg.get("screen_h")}')

    pipes.start(on_hello)

    # Spawn helper loop
    def spawn_loop():
        nonlocal helper_proc
        while pipes.running:
            helper_proc = spawn_helper_in_user_session()
            if helper_proc is None:
                log.warning('helper not spawned, retry in 5s')
                time.sleep(5)
                continue
            # Wait for helper to exit, then restart
            while pipes.running:
                code = helper_proc.poll()
                if code is not None:
                    log.warning(f'helper exited (code={code}); restarting')
                    break
                time.sleep(1)

    threading.Thread(target=spawn_loop, name='helper-spawner', daemon=True).start()

    # Main loop: read frames from pipe, forward to ... where? The original
    # agent.py had a WebSocket + DeltaScreenCapture. For now we just log
    # frame statistics. A future PR will wire WebSocket forwarding.
    frame_count = 0
    last_log = time.time()
    try:
        while pipes.running:
            frame = pipes.read_frame(timeout_ms=100)
            if frame is not None:
                frame_count += 1
                # In the real implementation: pipe this into DeltaScreenCapture
                # then send encoded delta via WebSocket.
            now = time.time()
            if now - last_log >= 30:
                log.info(f'frames received: {frame_count}')
                last_log = now
            time.sleep(0.01)
    except KeyboardInterrupt:
        log.info('service interrupted')
    finally:
        pipes.stop()
        if helper_proc:
            try: helper_proc.terminate()
            except Exception: pass
        log.info('service exiting')


if __name__ == '__main__':
    run()
