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


def clamp_to_screen(x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    x = max(0, min(int(x), w - 1))
    y = max(0, min(int(y), h - 1))
    return x, y


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
            # ctypes fallback: use VkKeyScan
            import ctypes
            vk = ctypes.windll.user32.VkKeyScanW(ord(key[0])) & 0xFF if len(key) == 1 else 0
            KEYEVENTF_KEYUP = 0x0002
            if action in ('press', 'down'):
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            if action in ('press', 'up'):
                ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    except Exception as e:
        log.warning(f'key error: {e}')


def hotkey(*keys: str):
    """Inject a hotkey (multiple keys pressed together)."""
    if not PYAUTOGUI_AVAILABLE:
        log.warning('no input backend for hotkey')
        return
    try:
        pyautogui.hotkey(*keys)
    except Exception as e:
        log.warning(f'hotkey error: {e}')


def type_text(text: str):
    """Type a string char by char."""
    if not PYAUTOGUI_AVAILABLE:
        log.warning('no input backend for type')
        return
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
