"""Mouse / keyboard / clipboard input injection.

Runs in the user session (helper). Uses pyautogui as the primary path
because it abstracts the cross-platform SendInput wrapping nicely.
Falls back to ctypes + win32api SendInput if pyautogui is not available.
"""
import logging
import time
from typing import Optional, Tuple

log = logging.getLogger('agent.input')

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import win32api
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# Mouse button VK codes (for GetAsyncKeyState verification of
# post-click button state)
_MOUSE_VK = {'left': 0x01, 'right': 0x02, 'middle': 0x04}

# Named key to VK code table for the ctypes fallback. Covers
# everything the App side actually sends (verified by reading
# remote_control_app/lib/features/remote/remote_page.dart:
# 'ctrl', 'alt', 'delete', 'tab', 'win', 'f1'-'f12', and the
# standard edit/navigation keys). The ctypes fallback used to
# have `vk = ... if len(key) == 1 else 0` which **silently
# dropped any named key** — bug discovered 2026-06-05 while
# auditing the production code path.
_NAMED_KEY_VK = {
    'backspace': 0x08, 'tab': 0x09,
    'enter': 0x0D, 'return': 0x0D, 'kp_enter': 0x0D,
    'shift': 0x10, 'shiftleft': 0xA0, 'shiftright': 0xA1,
    'ctrl': 0x11, 'control': 0x11, 'ctrlleft': 0xA2, 'ctrlright': 0xA3,
    'alt': 0x12, 'altleft': 0xA4, 'altright': 0xA5, 'menu': 0x12,
    'pause': 0x13, 'capslock': 0x14,
    'escape': 0x1B, 'esc': 0x1B,
    'space': 0x20, 'spacebar': 0x20,
    'pageup': 0x21, 'pagedown': 0x22, 'end': 0x23, 'home': 0x24,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'select': 0x29, 'print': 0x2A,
    'printscreen': 0x2C, 'prtsc': 0x2C,
    'insert': 0x2D, 'delete': 0x2E, 'del': 0x2E,
    'win': 0x5B, 'winleft': 0x5B, 'meta': 0x5B,
    'winright': 0x5C,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'numlock': 0x90, 'scrolllock': 0x91,
}


def clamp_to_screen(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    x = max(0, min(int(x), w - 1))
    y = max(0, min(int(y), h - 1))
    return x, y


def _get_async_key_state(vk: int) -> int:
    """GetAsyncKeyState: returns SHORT. High bit (0x8000) set = key
    is currently down. Low bit (0x0001) set = key was pressed since
    last call (we ignore this for verify purposes — we only care
    about the high bit).

    Module-level wrapper so tests can mock it without going through
    ctypes. Returns 0 (not down) if ctypes is unavailable so the
    caller treats "can't tell" as "probably fine".
    """
    try:
        import ctypes
        # GetAsyncKeyState returns SHORT (signed 16-bit). Mask to
        # unsigned to make bit-test consistent.
        return ctypes.windll.user32.GetAsyncKeyState(vk) & 0xFFFF
    except Exception as e:
        log.warning(f'_get_async_key_state({vk:#x}) failed: {e}')
        return 0


def is_button_up(button: str) -> bool:
    """Verify a mouse button is currently NOT pressed.

    After a click / mouseUp, the button MUST be UP. If still DOWN
    it means either:
      - SendInput is blocked (Session 0 / UAC / display lock) — the
        down half was a no-op so up was a no-op too, but the OS
        state is "not pressed" so the user just sees a missed click.
      - The 'up' half was lost (e.g. process suspended between
        down and up) — user sees the cursor "stuck" dragging
        whatever it landed on.

    Both look like a silent failure to the user. Returns False
    with a clear warning when detected.
    """
    vk = _MOUSE_VK.get(button)
    if vk is None:
        return True  # unknown button, can't verify
    state = _get_async_key_state(vk)
    if state & 0x8000:
        log.warning(
            f'is_button_up: {button} button is still DOWN '
            f'(GetAsyncKeyState=0x{state:04X}). '
            f'Likely Session 0 / UAC / display lock, OR '
            f'the mouseUp half of a click was lost.'
        )
        return False
    return True


def is_key_up(vk: int) -> bool:
    """Verify a virtual-key is currently NOT pressed.

    After a key press, the key should be UP. If still DOWN, the
    'up' half was lost — common with stuck-key symptoms in low-
    level keyboard hooks that are blocked by integrity level.
    Returns False with a clear warning when detected.
    """
    state = _get_async_key_state(vk)
    if state & 0x8000:
        log.warning(
            f'is_key_up: VK 0x{vk:02X} still DOWN '
            f'(GetAsyncKeyState=0x{state:04X}). '
            f'Likely Session 0 / UAC / display lock, OR '
            f'the keyUp half of a press was lost.'
        )
        return False
    return True


def _key_to_vk(key: str) -> Optional[int]:
    """Resolve a key name to its Windows virtual-key code.

    Used by the ctypes fallback (no pyautogui). Returns None if
    the key is unknown — caller should log and skip.

    For single-character keys: use VkKeyScanW which returns the
    VK code in the low byte and the shift state in the high byte.
    We strip the shift bit because keyDown / keyUp events for
    VK codes don't auto-press shift — the calling code should
    send shift separately if needed (rare; pyautogui handles
    this transparently in the primary path).

    For named keys: look up in _NAMED_KEY_VK. Match is case-
    insensitive since the App side sends both 'Ctrl' and 'ctrl'
    depending on the hotkey list source.
    """
    if not key:
        return None
    if len(key) == 1:
        try:
            import ctypes
            scan = ctypes.windll.user32.VkKeyScanW(ord(key))
            if scan == -1:
                return None  # no mapping (e.g. control char)
            return scan & 0xFF
        except Exception as e:
            log.warning(f'_key_to_vk: VkKeyScanW({key!r}) failed: {e}')
            return None
    # Named key: case-insensitive lookup
    return _NAMED_KEY_VK.get(key.lower())


def verify_at(x: int, y: int, tolerance: int = 2) -> bool:
    """Check that the OS cursor is actually at (x, y) right now.

    Why this matters
    ----------------
    SendInput (the underlying pyautogui / ctypes path) silently
    no-ops in three failure modes that look identical from the
    caller's perspective:
      1. Helper is running in Session 0 (SYSTEM) instead of the
         user's active session.
      2. UAC is blocking the call (different integrity level).
      3. The display is locked or no input desktop is attached.

    In all three, pyautogui.moveTo() returns successfully but
    `pyautogui.position()` afterwards still shows the old
    coordinates. Without a verify, the user sees "sendMouse: 100+"
    in the App log, "ws loop 481" on the server, and "last30s:
    cmds_recv=0" on the agent — the only signal being cursor
    doesn't move.

    Tolerance is in pixels (default 2) because of sub-pixel
    rounding in the SendInput normalized -> pixel conversion.

    Returns True if cursor is at (x, y) within tolerance, False
    otherwise. Logs a warning on mismatch with the actual vs
    expected position so silent failures are visible in the log.
    """
    if not PYAUTOGUI_AVAILABLE:
        # No way to read cursor without pyautogui / pywin32.
        # The test mocks pyautogui anyway, so this only matters
        # in production where pyautogui is the primary path.
        return True
    try:
        actual_x, actual_y = pyautogui.position()
    except Exception as e:
        log.warning(f'verify_at: cannot read cursor position: {e}')
        return False
    if abs(actual_x - x) > tolerance or abs(actual_y - y) > tolerance:
        log.warning(
            f'verify_at MISMATCH: expected=({x},{y}) actual=({actual_x},{actual_y}) '
            f'(tolerance={tolerance}). Likely Session 0 / UAC / display lock.'
        )
        return False
    return True


def mouse(x: int, y: int, button: str, action: str, screen_size: Tuple[int, int]):
    """Inject a mouse event. screen_size = (w, h) of primary display."""
    if not PYAUTOGUI_AVAILABLE and not WIN32_AVAILABLE:
        log.warning('no input backend available')
        return
    w, h = screen_size
    x, y = clamp_to_screen(x, y, w, h)
    btn = 'left' if button == 'left' else ('right' if button == 'right' else 'middle')

    try:
        if PYAUTOGUI_AVAILABLE:
            if action == 'move':
                pyautogui.moveTo(x, y, duration=0)
            elif action == 'down':
                pyautogui.mouseDown(x, y, button=btn)
            elif action == 'up':
                pyautogui.mouseUp(x, y, button=btn)
            elif action in ('click', 'double_click', 'dblclick', 'wheel'):
                if action == 'click':
                    pyautogui.click(x, y, button=btn)
                elif action in ('double_click', 'dblclick'):
                    pyautogui.doubleClick(x, y)
                elif action == 'wheel':
                    # msg.y is the wheel delta in the existing protocol
                    delta = int(y)
                    pyautogui.scroll(delta if delta >= 0 else -1, x=x, y=y)
        else:
            # ctypes win32 fallback
            import ctypes
            MOUSEEVENTF_MOVE     = 0x0001
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP   = 0x0004
            MOUSEEVENTF_RIGHTDOWN= 0x0008
            MOUSEEVENTF_RIGHTUP  = 0x0010
            MOUSEEVENTF_WHEEL    = 0x0800
            MOUSEEVENTF_ABSOLUTE = 0x8000
            down_flag = MOUSEEVENTF_LEFTDOWN if btn == 'left' else MOUSEEVENTF_RIGHTDOWN
            up_flag   = MOUSEEVENTF_LEFTUP   if btn == 'left' else MOUSEEVENTF_RIGHTUP
            # 65535 = MAX_COORD in normalized absolute mode
            nx = int(x * 65535 / (w - 1)) if w > 1 else 0
            ny = int(y * 65535 / (h - 1)) if h > 1 else 0
            if action in ('move', 'down', 'click', 'double_click', 'dblclick'):
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny, 0, 0)
            if action in ('down', 'click', 'double_click', 'dblclick'):
                ctypes.windll.user32.mouse_event(down_flag, nx, ny, 0, 0)
            if action in ('up', 'click', 'double_click', 'dblclick'):
                ctypes.windll.user32.mouse_event(up_flag, nx, ny, 0, 0)
        # After-action observability: log what we did, and verify
        # wherever the verify has actual signal-to-noise:
        #   - 'move' / 'click' / 'dblclick' / 'down' -> verify cursor
        #     is at (x, y) (catches SendInput silent no-op in
        #     Session 0 / UAC / display-lock scenarios)
        #   - 'click' / 'dblclick' / 'up' -> verify the button
        #     is UP (catches 'up half lost' scenarios where the
        #     cursor moves but mouseUp silently no-ops, leaving
        #     a stuck drag)
        #   - 'wheel' -> no position target, skip
        if action in ('move', 'click', 'double_click', 'dblclick', 'down'):
            verify_at(x, y)
        if action in ('click', 'double_click', 'dblclick', 'up'):
            is_button_up(btn)
        if action not in ('move', 'click', 'double_click', 'dblclick', 'down', 'up', 'wheel'):
            log.info(
                f'mouse {action} ({x},{y}) {btn} via '
                f'{"pyautogui" if PYAUTOGUI_AVAILABLE else "ctypes"}'
            )
    except Exception as e:
        log.warning(f'mouse error: {e}')


def key(key: str, action: str):
    """Inject a key event."""
    if not PYAUTOGUI_AVAILABLE and not WIN32_AVAILABLE:
        log.warning('no input backend available')
        return
    log.info(f'key {action} "{key}" via {"pyautogui" if PYAUTOGUI_AVAILABLE else "ctypes"}')
    try:
        if PYAUTOGUI_AVAILABLE:
            if action in ('press', 'down'):
                pyautogui.keyDown(key)
                if action == 'press':
                    pyautogui.keyUp(key)
            elif action == 'up':
                pyautogui.keyUp(key)
        else:
            # ctypes fallback: use _key_to_vk for both named and
            # single-character keys. (The old code's
            # `vk = ... if len(key) == 1 else 0` silently dropped
            # every named key — bug fixed 2026-06-05.)
            import ctypes
            vk = _key_to_vk(key)
            if vk is None:
                log.warning(f'key: no VK mapping for "{key}", skipping')
                return
            KEYEVENTF_KEYUP = 0x0002
            if action in ('press', 'down'):
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            if action in ('press', 'up'):
                ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        # After-action observability: for 'press' (the only action
        # that's a complete down+up cycle), verify the key is UP
        # afterwards. 'down' and 'up' are half-cycles, the key
        # SHOULD be down/up respectively, so no verify.
        if action == 'press':
            vk = _key_to_vk(key)
            if vk is not None:
                is_key_up(vk)
    except Exception as e:
        log.warning(f'key error: {e}')


def hotkey(*keys: str):
    """Inject a hotkey (multiple keys pressed together)."""
    if not PYAUTOGUI_AVAILABLE:
        log.warning('no input backend for hotkey')
        return
    log.info(f'hotkey {"+".join(keys)} via pyautogui')
    try:
        pyautogui.hotkey(*keys)
    except Exception as e:
        log.warning(f'hotkey error: {e}')


def type_text(text: str):
    """Type a string char by char."""
    if not PYAUTOGUI_AVAILABLE:
        log.warning('no input backend for type')
        return
    log.info(f'type_text len={len(text)} preview="{(text[:30] + "...") if len(text) > 30 else text}"')
    try:
        # interval=0 for speed; pyautogui.write handles unicode reasonably
        pyautogui.write(text, interval=0)
    except Exception as e:
        log.warning(f'type error: {e}')


def clipboard_set(text: str):
    """Set clipboard text. Used for cross-platform copy."""
    if not WIN32_AVAILABLE:
        log.warning('no win32 backend for clipboard')
        return
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text)
        win32clipboard.CloseClipboard()
    except Exception as e:
        log.warning(f'clipboard set error: {e}')
