"""IPC protocol for service <-> helper communication over named pipes.

Two named pipes separate control flow from high-volume frame data:
  - CMD_PIPE:   bidirectional JSON messages (small, latency-sensitive)
  - FRAME_PIPE: helper -> service only, binary frames (large, throughput-sensitive)

Wire format: [4-byte big-endian length][body bytes]
  - body on cmd pipe is UTF-8 JSON
  - body on frame pipe is raw BGRA/RGB bytes
"""
import json
import struct
import logging
from typing import Optional

# Pipe names. Local to the user session; only service and helper on same machine
# connect, so global namespace is safe.
CMD_PIPE   = r'\\.\pipe\RemoteControlAgent_Cmd'
FRAME_PIPE = r'\\.\pipe\RemoteControlAgent_Frame'

# IPC authentication token (generated per service start; helper inherits from
# command-line arg). Prevents random local users from injecting commands.
# This is NOT a security boundary - it's defense against accidents only.
AUTH_TOKEN_LENGTH = 32

# Message types on cmd pipe
MSG_HELLO            = 'hello'             # helper -> service (greeting + auth)
MSG_HELLO_ACK        = 'hello_ack'         # service -> helper
MSG_HEARTBEAT        = 'heartbeat'         # both ways
MSG_BYE              = 'bye'               # helper -> service (clean exit)

# Service -> helper
MSG_INPUT_MOUSE      = 'input_mouse'       # {x, y, button, action}
MSG_INPUT_KEY        = 'input_key'         # {key, action}
MSG_INPUT_HOTKEY     = 'input_hotkey'      # {keys: [...]}
MSG_INPUT_TYPE       = 'input_type'        # {text: "..."}
MSG_INPUT_CLIPBOARD_SET = 'input_clipboard_set'  # {text: "..."}
MSG_INPUT_EXEC       = 'input_exec'        # {cmd, session_id} (shell exec in helper)
MSG_INPUT_FILE_DOWNLOAD = 'input_file_download'  # {path, filename, session_id}
MSG_INPUT_FILE_UPLOAD   = 'input_file_upload'    # {filename, target_path, chunk, is_last, session_id}
MSG_FPS_BACKOFF      = 'fps_backoff'       # {reason, qsize, drops}
                                          # Service -> helper: outgoing_q is
                                          # above high-watermark; please drop
                                          # capture fps by ~50% for 2s. The
                                          # helper is expected to halve its
                                          # capture loop sleep until it sees
                                          # a clear signal (no backoff for 5s).

# Helper -> service
MSG_CAPTURE_BATCH    = 'capture_batch'     # {frames: [{seq, ts, w, h, fmt, delta}, ...]}
MSG_EXEC_RESULT      = 'exec_result'       # {session_id, output, exit_code}
MSG_FILE_DOWNLOAD_READY = 'file_download_ready'  # {session_id, filename, total_size}
MSG_FILE_DOWNLOAD_CHUNK  = 'file_download_chunk' # {session_id, offset, data_b64, is_last}
MSG_FILE_UPLOAD_ACK  = 'file_upload_ack'   # {session_id, status, path}
MSG_STATUS           = 'status'            # {backend, screen_w, screen_h, capture_fps, ...}

# Frame header length (uint32 BE)
LEN_FMT = '>I'
LEN_SIZE = 4

log = logging.getLogger('agent.ipc')


def _read_exact(handle, n: int) -> Optional[bytes]:
    """Read exactly n bytes from a win32file handle. None on EOF/closed pipe.

    Works with PIPE_BYTE_STREAM pipes: ReadFile may return fewer than n bytes,
    so we loop until we accumulate n bytes.
    """
    import win32file  # type: ignore
    buf = b''
    while len(buf) < n:
        try:
            hr, chunk = win32file.ReadFile(handle, n - len(buf))
            if hr != 0 and hr != 234:  # 234 = ERROR_MORE_DATA (legacy)
                return None
            if not chunk:
                return None
            buf += chunk
        except Exception:
            return None
    return buf


def pack(obj_or_bytes) -> bytes:
    """Wrap a dict (JSON) or raw bytes in a length-prefixed envelope."""
    if isinstance(obj_or_bytes, (dict, list)):
        body = json.dumps(obj_or_bytes, ensure_ascii=False).encode('utf-8')
    elif isinstance(obj_or_bytes, str):
        body = obj_or_bytes.encode('utf-8')
    elif isinstance(obj_or_bytes, bytes):
        body = obj_or_bytes
    else:
        raise TypeError(f'cannot pack {type(obj_or_bytes)}')
    return struct.pack(LEN_FMT, len(body)) + body


def read_envelope(handle) -> Optional[bytes]:
    """Read one length-prefixed envelope body. None on EOF or timeout."""
    header = _read_exact(handle, LEN_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack(LEN_FMT, header)
    return _read_exact(handle, length)


def read_msg(handle) -> Optional[dict]:
    """Read one length-prefixed JSON message. None on EOF."""
    body = read_envelope(handle)
    if body is None:
        return None
    try:
        return json.loads(body.decode('utf-8'))
    except Exception as e:
        log.warning(f'malformed message: {e}')
        return None


def send_msg(handle, msg: dict) -> None:
    """Send a length-prefixed JSON message. Raises on error."""
    import win32file  # type: ignore
    data = pack(msg)
    err, written = win32file.WriteFile(handle, data)
    if err != 0 and err != 234:  # 234 = ERROR_MORE_DATA (legacy message-mode)
        raise IOError(f'WriteFile failed: err={err} written={written}/{len(data)}')
    if written != len(data):
        raise IOError(f'WriteFile short write: {written}/{len(data)}')


def send_frame(handle, data: bytes) -> None:
    """Send a length-prefixed binary frame. Raises on error."""
    import win32file  # type: ignore
    err, written = win32file.WriteFile(handle, pack(data))
    if err != 0 and err != 234:
        raise IOError(f'WriteFile failed: err={err} written={written}/{len(data)+4}')
    # Note: pack() adds 4 length bytes; we don't verify written == len(data)+4 because
    # the framing is the responsibility of the protocol, not the transport.
