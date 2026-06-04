"""Helper process - runs in the user's interactive session (Session 1+).

Responsibilities:
  - Capture screen (DXGI / mss / PIL fallback)
  - Inject input (mouse / keyboard / clipboard)
  - Execute shell commands on behalf of the service
  - Read files for download, write files for upload
  - Speak to the service over two named pipes (cmd + frame)

The service is responsible for everything else: WebSocket, auth, file
transfer chunking, etc.
"""
import os
import sys
import time
import json
import struct
import base64
import socket
import logging
import platform
import subprocess
import threading

# Make sure we can find sibling modules whether invoked as module or script
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from agent import protocol as ipc
from agent import capture as cap
from agent import input_inject as inp
from agent.enhanced_screen import DeltaScreenCapture

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [helper %(levelname)s] %(message)s',
)
log = logging.getLogger('helper')

AUTH_TOKEN = os.environ.get('RC_HELPER_TOKEN', '')
START_TS = time.time()


# ============================================================
# Click markers: visible visual feedback on the captured screen
# ============================================================
# When a mouse-down (or click / double_click) event arrives from
# the App, we record the (x, y) in desktop pixel coordinates and
# draw a bright red ring + crosshair + coordinate text on the
# next ~1.5 seconds of captured frames. This makes the
# App -> desktop coordinate mapping immediately observable: the
# user can tell at a glance whether the click landed where they
# expected, and if not, how far off (in pixels) it landed.
#
# The marker is drawn on the CAPTURED frame buffer, before
# encoding, so it shows up in the App itself -- no need to look
# at the actual Windows desktop. (The same approach could be
# used to draw on the real desktop via a transparent overlay
# window, but that would race with the user actually clicking
# on the desktop, and would add a click-through-anything
# overlay that can be confusing.)

_MARKER_DURATION_S = 1.5
_MARKER_RADIUS_PX = 60   # outer ring radius in DESKTOP pixels
_MARKER_RING_WIDTH = 8
_MARKER_CROSSHAIR_LEN = 40
_markers: list = []  # list of (x, y, button, expires_at)
_markers_lock = threading.Lock()


def _record_click(x: int, y: int, button: str) -> None:
    """Push a new click marker. The frame_sender will draw it on
    subsequent frames for ~1.5s."""
    expires = time.time() + _MARKER_DURATION_S
    with _markers_lock:
        _markers.append((int(x), int(y), button, expires))
    log.info(f'CLICK MARKER at desktop ({x}, {y}) button={button}')


def _draw_markers(img) -> None:
    """Draw all live markers onto the given PIL Image (in-place).
    Removes expired markers. Pure-PIL drawing -- no extra deps."""
    from PIL import ImageDraw, ImageFont
    now = time.time()
    with _markers_lock:
        live = [m for m in _markers if m[3] > now]
        # mutate in place so we don't keep growing
        _markers[:] = live
    if not live:
        return
    draw = ImageDraw.Draw(img, 'RGBA')
    # Try to load a font, fall back to default
    font = None
    for path in (
        r'C:\Windows\Fonts\consolab.ttf',  # Consolas Bold
        r'C:\Windows\Fonts\consola.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
        r'C:\Windows\Fonts\arial.ttf',
    ):
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 24)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    w, h = img.size
    for (x, y, btn, _exp) in live:
        # Cull out markers that landed outside the screen -- the
        # user can't see them anyway and drawing them risks PIL
        # blowing up on negative ellipse args.
        if x < -_MARKER_RADIUS_PX or y < -_MARKER_RADIUS_PX \
                or x > w + _MARKER_RADIUS_PX or y > h + _MARKER_RADIUS_PX:
            continue
        r = _MARKER_RADIUS_PX
        cw = _MARKER_RING_WIDTH
        cl = _MARKER_CROSSHAIR_LEN
        # Bright red ring (outer + inner alpha so the ring is
        # visible against bright desktop backgrounds like
        # white windows)
        ring_box = (x - r, y - r, x + r, y + r)
        draw.ellipse(ring_box, outline=(255, 0, 0, 255), width=cw)
        # Crosshair through the center, going from -cl to +cl
        draw.line([(x - cl, y), (x + cl, y)], fill=(255, 0, 0, 255), width=4)
        draw.line([(x, y - cl), (x, y + cl)], fill=(255, 0, 0, 255), width=4)
        # Center dot
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 0, 0, 255))
        # Coordinate label just above the ring (or below if
        # we're near the top of the screen)
        label = f'({x},{y}) {btn}'
        # Use textbbox for accurate sizing
        try:
            tb = draw.textbbox((0, 0), label, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = 200, 28
        lx = x - tw // 2
        ly = y - r - th - 8 if y - r - th - 8 > 0 else y + r + 8
        # Black outline so the text is readable on any background
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((lx + dx, ly + dy), label, font=font,
                          fill=(0, 0, 0, 255))
        draw.text((lx, ly), label, font=font, fill=(255, 255, 0, 255))


def connect_pipe(name: str, retries: int = 30, delay: float = 0.5):
    """Connect to a named pipe with retry. Returns the pipe handle or None."""
    import pywintypes  # type: ignore
    import win32file  # type: ignore
    import win32pipe  # type: ignore
    GENERIC_READ  = win32file.GENERIC_READ
    GENERIC_WRITE = win32file.GENERIC_WRITE
    OPEN_EXISTING = win32file.OPEN_EXISTING
    for i in range(retries):
        try:
            h = win32file.CreateFile(
                name,
                GENERIC_READ | GENERIC_WRITE,
                0,  # no sharing
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            return h
        except pywintypes.error as e:
            if e.winerror == 2:  # ERROR_FILE_NOT_FOUND - service not ready
                time.sleep(delay)
                continue
            raise
    return None


def frame_sender(stop_event: threading.Event):
    """Background thread: grab frames, run through DeltaScreenCapture,
    send encoded JPEGs (keyframe or delta) to the service frame pipe.

    Frame envelope (16-byte header + JSON body):
      [4 bytes length BE] [4 bytes seq BE] [8 bytes ts BE] [JSON utf-8]

    JSON body is a DeltaScreenCapture message dict:
      keyframe: {type:'screen', fmt:'kf', data:base64(jpeg), w, h, ts}
      delta:    {type:'screen', fmt:'df', data:base64(pixel_data),
                 regions:[[x,y,w,h],...], w, h, ts, blocks:N}
      skip:     (not sent - delta has no changes)

    The service just forwards the message dict over WS to the VPS relay.
    """
    sc = cap.ScreenCapture()
    log.info(f'frame_sender: backend={sc.backend} size={sc.width}x{sc.height}')

    import win32file  # type: ignore
    import win32pipe  # type: ignore
    GENERIC_WRITE = win32file.GENERIC_WRITE
    OPEN_EXISTING = win32file.OPEN_EXISTING

    delta = DeltaScreenCapture(sc.width, sc.height)

    # Open frame pipe (write only)
    handle = None
    while handle is None and not stop_event.is_set():
        try:
            handle = win32file.CreateFile(
                ipc.FRAME_PIPE,
                GENERIC_WRITE,
                0, None,
                OPEN_EXISTING, 0, None,
            )
        except Exception as e:
            log.debug(f'frame pipe not ready: {e}')
            time.sleep(0.5)
    if handle is None:
        log.error('frame_sender: failed to open frame pipe')
        sc.close()
        return

    log.info('frame_sender: connected to frame pipe')
    fps_target = float(os.environ.get('SCREEN_FPS', '5'))
    interval = 1.0 / fps_target

    seq = 0
    kf_count = 0
    df_count = 0
    skip_count = 0
    try:
        while not stop_event.is_set():
            t0 = time.time()
            arr = sc.grab()
            if arr is not None:
                # Convert numpy RGB to PIL Image for DeltaScreenCapture.
                from PIL import Image
                img = Image.fromarray(arr)
                # Overlay any live click markers so the user can see
                # exactly where the App's click landed on the desktop.
                # Markers are recorded by _record_click() from
                # cmd_loop's input_mouse handler. Drawn here on the
                # raw frame BEFORE DeltaScreenCapture splits it into
                # kf/df regions, so the marker survives the delta
                # encoding (it just becomes part of the changed
                # pixels and the server pushes a df update).
                _draw_markers(img)
                msg = delta.capture_and_encode()
                if msg is None:
                    skip_count += 1
                else:
                    body = json.dumps(msg, ensure_ascii=False).encode('utf-8')
                    # 16-byte header: 4 length, 4 seq, 8 ts
                    header = struct.pack('>IIQ',
                                         len(body),
                                         seq,
                                         int(t0 * 1000))
                    ipc.send_frame(handle, header + body)
                    if msg.get('fmt') == 'kf':
                        kf_count += 1
                    else:
                        df_count += 1
                    seq += 1
                    if seq % 50 == 0:
                        log.info(f'frame_sender stats: seq={seq} kf={kf_count} '
                                 f'df={df_count} skip={skip_count}')
            elapsed = time.time() - t0
            time.sleep(max(0, interval - elapsed))
    except Exception as e:
        log.warning(f'frame_sender error: {e}')
    finally:
        try:
            win32pipe.CloseHandle(handle)
        except Exception:
            pass
        sc.close()


def handle_cmd_message(msg: dict, screen_size, helper_id: str) -> dict:
    """Process a control message from the service. Return any reply (or None)."""
    t = msg.get('type')
    # One line per inbound cmd so the operator can see exactly what the
    # helper is acting on. Use a 'cmd' prefix to keep it distinct from
    # frame/capture logs.
    if t and t != ipc.MSG_HEARTBEAT:
        # Truncate any payload fields that might be large (file data,
        # big pastes) so a 10MB file upload doesn't drown the log.
        compact = {k: (v[:80] + '...') if isinstance(v, str) and len(v) > 80 else v
                   for k, v in msg.items() if k != 'type'}
        log.info(f'cmd: {t} {compact}')
    try:
        if t == ipc.MSG_HEARTBEAT:
            return {'type': ipc.MSG_HEARTBEAT, 'ts': time.time()}

        elif t == ipc.MSG_INPUT_MOUSE:
            x, y = msg['x'], msg['y']
            btn = msg.get('button', 'left')
            act = msg.get('action', 'move')
            inp.mouse(x, y, btn, act, screen_size)
            # Record a click marker on the captured screen so the
            # user can SEE where the click actually landed in
            # desktop pixel coordinates. Useful for debugging the
            # App -> desktop coordinate mapping (letterbox, scale,
            # zoom). Drawn for ~1.5s as a red ring + crosshair +
            # coordinate text. We only mark button-down events --
            # pure 'move' would flood the queue with markers and
            # would just be visual noise.
            if act in ('down', 'click', 'double_click'):
                _record_click(x, y, btn)
            return None

        elif t == ipc.MSG_INPUT_KEY:
            inp.key(msg.get('key', ''), msg.get('action', 'press'))
            return None

        elif t == ipc.MSG_INPUT_HOTKEY:
            inp.hotkey(*msg.get('keys', []))
            return None

        elif t == ipc.MSG_INPUT_TYPE:
            inp.type_text(msg.get('text', ''))
            return None

        elif t == ipc.MSG_INPUT_CLIPBOARD_SET:
            inp.clipboard_set(msg.get('text', ''))
            return None

        elif t == ipc.MSG_INPUT_EXEC:
            return _do_exec(msg)

        elif t == ipc.MSG_INPUT_FILE_DOWNLOAD:
            return _do_file_download(msg)

        elif t == ipc.MSG_INPUT_FILE_UPLOAD:
            return _do_file_upload(msg)

        else:
            log.warning(f'unknown message type: {t}')
            return None
    except Exception as e:
        log.warning(f'handle {t} error: {e}')
        return {'type': 'error', 'error': str(e), 'orig_type': t}


def _do_exec(msg: dict) -> dict:
    """Run a shell command. Returns exec_result."""
    session_id = msg.get('session_id', '')
    cmd = msg.get('cmd', '')
    try:
        # shell=True on Windows uses cmd.exe which is the historical behavior.
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=60, encoding='utf-8', errors='replace',
        )
        return {
            'type': ipc.MSG_EXEC_RESULT,
            'session_id': session_id,
            'output': result.stdout + result.stderr,
            'exit_code': result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            'type': ipc.MSG_EXEC_RESULT,
            'session_id': session_id,
            'output': '(timeout after 60s)',
            'exit_code': 124,
        }
    except Exception as e:
        return {
            'type': ipc.MSG_EXEC_RESULT,
            'session_id': session_id,
            'output': f'(exec error: {e})',
            'exit_code': 1,
        }


def _do_file_download(msg: dict) -> dict:
    """Read a file from disk and stream chunks back to the service."""
    path = msg.get('path', '')
    filename = msg.get('filename', os.path.basename(path))
    session_id = msg.get('session_id', '')
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            # Tell service the file is ready (with total size)
            yield {
                'type': ipc.MSG_FILE_DOWNLOAD_READY,
                'session_id': session_id,
                'filename': filename,
                'total_size': size,
            }
            offset = 0
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield {
                    'type': ipc.MSG_FILE_DOWNLOAD_CHUNK,
                    'session_id': session_id,
                    'offset': offset,
                    'data_b64': base64.b64encode(chunk).decode('ascii'),
                    'is_last': False,
                }
                offset += len(chunk)
            yield {
                'type': ipc.MSG_FILE_DOWNLOAD_CHUNK,
                'session_id': session_id,
                'offset': offset,
                'data_b64': '',
                'is_last': True,
            }
    except Exception as e:
        yield {
            'type': ipc.MSG_FILE_DOWNLOAD_READY,
            'session_id': session_id,
            'filename': filename,
            'total_size': 0,
            'error': str(e),
        }


def _do_file_upload(msg: dict) -> dict:
    """Append a chunk to an upload buffer keyed by (session_id, path)."""
    # This is stateful - kept simple for now, full state mgmt in service.
    path = msg.get('target_path', '')
    session_id = msg.get('session_id', '')
    chunk = base64.b64decode(msg.get('chunk', '')) if msg.get('chunk') else b''
    is_last = msg.get('is_last', False)
    try:
        if msg.get('start', False):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(chunk)
        else:
            with open(path, 'ab') as f:
                f.write(chunk)
        return {
            'type': ipc.MSG_FILE_UPLOAD_ACK,
            'session_id': session_id,
            'path': path,
            'status': 'ok',
            'is_last': is_last,
        }
    except Exception as e:
        return {
            'type': ipc.MSG_FILE_UPLOAD_ACK,
            'session_id': session_id,
            'path': path,
            'status': 'error',
            'error': str(e),
        }


def cmd_loop(stop_event: threading.Event, screen_size, helper_id: str):
    """Main loop: connect to cmd pipe, process messages."""
    import win32file  # type: ignore
    handle = connect_pipe(ipc.CMD_PIPE)
    if handle is None:
        log.error('cmd_loop: failed to connect to cmd pipe')
        return
    log.info('cmd_loop: connected to cmd pipe')

    # Send HELLO with auth token
    ipc.send_msg(handle, {
        'type': ipc.MSG_HELLO,
        'token': AUTH_TOKEN,
        'pid': os.getpid(),
        'session_id': _get_session_id(),
        'user': _get_user_name(),
        'backend': _capture_backend(),
        'screen_w': screen_size[0],
        'screen_h': screen_size[1],
        'start_ts': START_TS,
    })

    try:
        while not stop_event.is_set():
            msg = ipc.read_msg(handle)
            if msg is None:
                log.info('cmd pipe closed by service')
                break
            # Replies can be a single dict or a generator (for downloads)
            result = handle_cmd_message(msg, screen_size, helper_id)
            if result is None:
                continue
            if hasattr(result, '__iter__') and not isinstance(result, dict):
                # Generator of replies
                for r in result:
                    ipc.send_msg(handle, r)
            else:
                ipc.send_msg(handle, result)
    except Exception as e:
        log.warning(f'cmd_loop error: {e}')
    finally:
        try:
            win32file.CloseHandle(handle)
        except Exception:
            pass
        stop_event.set()


def _get_session_id() -> int:
    """Get current process session ID via kernel32."""
    try:
        import ctypes
        return ctypes.windll.kernel32.WTSGetActiveConsoleSessionId()
    except Exception:
        return 0


def _get_user_name() -> str:
    try:
        return os.environ.get('USERNAME', '') or os.getlogin()
    except Exception:
        return ''


def _capture_backend() -> str:
    try:
        return cap.ScreenCapture().backend
    except Exception:
        return 'none'


def run():
    log.info('helper starting...')
    log.info(f'auth token present: {bool(AUTH_TOKEN)}')
    log.info(f'session: {_get_session_id()} user: {_get_user_name()}')

    # Initial capture to determine backend + size
    try:
        sc = cap.ScreenCapture()
        screen_size = (sc.width, sc.height)
        sc.close()
    except Exception as e:
        log.error(f'capture init failed: {e}')
        screen_size = (1920, 1080)

    stop_event = threading.Event()

    # Start frame sender in background
    ft = threading.Thread(target=frame_sender, args=(stop_event,),
                          name='frame-sender', daemon=True)
    ft.start()

    # Cmd loop blocks
    try:
        cmd_loop(stop_event, screen_size, 'helper')
    except KeyboardInterrupt:
        log.info('helper interrupted')
    finally:
        stop_event.set()
        log.info('helper exiting')
        time.sleep(0.5)


if __name__ == '__main__':
    run()
