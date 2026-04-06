#!/usr/bin/env python3
"""
Remote Control Windows Agent - Desktop Application
==================================================
Features:
- System tray icon with context menu
- Auto-start on Windows boot
- Background running (no console window)
- WebSocket connection to relay server
- Screen capture & streaming
- Mouse/keyboard input simulation
- Shell command execution
- File transfer
"""

import sys
import os
import json
import time
import base64
import uuid
import socket
import struct
import hashlib
import logging
import threading
import subprocess
import tempfile
import webbrowser
import urllib.request
import urllib.error
from datetime import datetime

# ---- Optional imports ----
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = hasattr(mss, 'mss')  # Check if old API exists
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Enhanced screen capture with delta frames
try:
    from enhanced_screen import DeltaScreenCapture, get_screen_size
except ImportError:
    DeltaScreenCapture = None
    logging.warning("enhanced_screen module not found")

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import win32api, win32con, win32gui, win32clipboard, win32event, win32process
    import win32com.client
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import websocket
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

try:
    import pythoncom
    PYTHONCOM_AVAILABLE = True
except ImportError:
    PYTHONCOM_AVAILABLE = False

# ============================================================
# Constants
# ============================================================

APP_NAME = "RemoteControlAgent"
APP_VERSION = "1.0.0"
CONFIG_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, 'agent.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'agent.log')
SERVER_URL = os.environ.get('RC_SERVER', 'ws://8.137.116.121:9080/agent')
SCREEN_QUALITY = int(os.environ.get('SCREEN_QUALITY', '60'))
SCREEN_FPS = float(os.environ.get('SCREEN_FPS', '5'))

# Tray icon paths
ICON_PATH = os.path.join(CONFIG_DIR, 'icon.ico')
if not os.path.exists(ICON_PATH):
    ICON_PATH = None  # Will use default

# ============================================================
# Logging
# ============================================================

def setup_logging():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    # Use simple file handler that flushes immediately
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    fh.setLevel(logging.INFO)
    # Console handler (suppressed in windowed mode)
    if IS_WINDOWED:
        try:
            ch = logging.StreamHandler(sys.stdout)
        except Exception:
            ch = logging.StreamHandler(open(os.devnull, 'w'))
    else:
        ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)

IS_WINDOWED = sys.executable.endswith('pythonw.exe') or '--windowed' in sys.argv

# ============================================================
# Config Management
# ============================================================

def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def _get_machine_fingerprint():
    """Generate a deterministic machine fingerprint from NIC MAC + hostname.
    This ensures the same PC always gets the same agent_id, even after config reset.
    """
    hostname = socket.gethostname()
    if PSUTIL_AVAILABLE:
        try:
            import uuid as _uuid_module
            # Get first non-loopback MAC address
            for iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == _uuid_module.AF_LINK and addr.address not in ('00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff'):
                        mac = addr.address.replace(':', '')
                        fingerprint = f"{hostname}-{mac}"
                        return hashlib.sha1(fingerprint.encode()).hexdigest()[:16]
        except Exception:
            pass
    # Fallback: just use hostname
    return hashlib.sha1(hostname.encode()).hexdigest()[:16]

def get_or_create_credentials():
    cfg = load_config()
    if cfg.get('agent_id') and cfg.get('secret'):
        return cfg['agent_id'], cfg['secret'], cfg.get('server_url', SERVER_URL)
    
    hostname = socket.gethostname()
    try:
        import platform
        os_name = f"Windows {platform.release()}"
    except Exception:
        os_name = "Windows"
    
    # Use machine fingerprint to generate deterministic ID and secret
    # (stable across restarts/reinstalls - same machine always = same identity)
    fingerprint = _get_machine_fingerprint()
    agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{hostname}-{fingerprint}"))
    secret = hashlib.sha256(f"{hostname}-{fingerprint}".encode()).hexdigest()[:16]
    server_url = SERVER_URL
    
    cfg = {
        'agent_id': agent_id,
        'secret': secret,
        'hostname': hostname,
        'os': os_name,
        'server_url': server_url,
        'auto_start': False,
        'first_run': datetime.now().isoformat()
    }
    save_config(cfg)
    return agent_id, secret, server_url

def set_auto_start(enable=True):
    """Add or remove from Windows startup via registry."""
    if not WIN32_AVAILABLE:
        logging.warning("win32 not available, cannot set auto-start")
        return
    
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            exe_path = sys.executable
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}" --minimized')
            logging.info(f"Auto-start enabled: {exe_path}")
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        
        cfg = load_config()
        cfg['auto_start'] = enable
        save_config(cfg)
    except Exception as e:
        logging.error(f"Failed to set auto-start: {e}")

def get_screen_size():
    if PYAUTOGUI_AVAILABLE:
        return pyautogui.size()
    if WIN32_AVAILABLE:
        return (win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))
    return (1920, 1080)

# ============================================================
# Screen Capture
# ============================================================

class ScreenCapture:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_frame = None
        logging.info("Screen capture: PIL")
    
    def capture(self):
        """Capture screen, return JPEG bytes or None."""
        try:
            frame = ImageGrab.grab()
            import io
            buf = io.BytesIO()
            frame.save(buf, format='JPEG', quality=SCREEN_QUALITY)
            return buf.getvalue()
        except Exception as e:
            logging.warning(f"Screen capture error: {e}")
            return None

# ============================================================
# Input Simulation
# ============================================================

KEY_MAP = {
    'enter': 0x0D, 'return': 0x0D,
    'tab': 0x09, 'escape': 0x1B, 'esc': 0x1B,
    'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12,
    'win': 0x5B, 'windows': 0x5B,
    'backspace': 0x08, 'delete': 0x2E, 'del': 0x2E,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'space': 0x20,
}

def parse_key(key):
    k = key.lower()
    if k in KEY_MAP:
        return KEY_MAP[k]
    if len(k) == 1:
        vk = win32api.VkKeyScan(k) if WIN32_AVAILABLE else 0
        return vk & 0xFF
    return None

def handle_mouse(x, y, button, action):
    if not PYAUTOGUI_AVAILABLE:
        return
    
    w, h = get_screen_size()
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    
    try:
        if action == 'move':
            pyautogui.moveTo(x, y, duration=0)
        elif action == 'down':
            btn = 'left' if button == 'left' else 'right'
            pyautogui.mouseDown(x, y, btn)
        elif action == 'up':
            btn = 'left' if button == 'left' else 'right'
            pyautogui.mouseUp(x, y, btn)
        elif action == 'click':
            btn = 'left' if button == 'left' else 'right'
            pyautogui.click(x, y, button=btn)
        elif action == 'double_click' or action == 'dblclick':
            pyautogui.doubleClick(x, y)
        elif action == 'wheel':
            pyautogui.scroll(y if y > 0 else -1, x=x, y=y)
    except Exception as e:
        logging.warning(f"Mouse error: {e}")

def handle_key(key, action):
    if not PYAUTOGUI_AVAILABLE:
        return
    
    vk = parse_key(key)
    if vk is None:
        logging.warning(f"Unknown key: {key}")
        return
    
    try:
        if action in ('press', 'down'):
            pyautogui.keyDown(key)
            if action == 'press':
                pyautogui.keyUp(key)
        elif action == 'up':
            pyautogui.keyUp(key)
    except Exception as e:
        logging.warning(f"Key error: {e}")

def handle_hotkey(*keys):
    if PYAUTOGUI_AVAILABLE:
        try:
            pyautogui.hotkey(*keys)
        except Exception as e:
            logging.warning(f"Hotkey error: {e}")

# ============================================================
# Shell Execution
# =========================================================>

def execute_command(cmd, session_id, send_fn):
    if not cmd:
        send_fn({'type': 'output', 'session': session_id, 'data': '', 'done': True})
        return
    
    try:
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            ['powershell', '-NoProfile', '-NoEncoding', '-Command', cmd],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            try:
                text = chunk.decode('utf-8', errors='replace')
                send_fn({'type': 'output', 'session': session_id, 'data': text, 'done': False})
            except Exception:
                pass
        
        proc.wait()
        send_fn({'type': 'output', 'session': session_id, 'data': '', 'done': True})
    except Exception as e:
        send_fn({'type': 'output', 'session': session_id, 'data': f'Error: {e}', 'done': True})

# ============================================================
# File Transfer
# ============================================================

def handle_file_download(path, session_id, filename, send_fn):
    try:
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            send_fn({'type': 'output', 'session': session_id, 'data': f'File not found: {path}', 'done': True})
            return
        
        size = os.path.getsize(path)
        logging.info(f"Download: {path} ({size} bytes)")
        chunk_size = 32768
        
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                b64 = base64.b64encode(chunk).decode('ascii')
                send_fn({'type': 'file_chunk', 'session': session_id, 'chunk': b64, 'done': False, 'filename': filename or os.path.basename(path)})
                time.sleep(0.01)
        
        send_fn({'type': 'file_chunk', 'session': session_id, 'chunk': '', 'done': True, 'filename': filename or os.path.basename(path)})
    except Exception as e:
        logging.error(f"Download error: {e}")
        send_fn({'type': 'output', 'session': session_id, 'data': f'Download error: {e}', 'done': True})

# ============================================================
# WebSocket Client
# ============================================================

class WebSocketClient:
    def __init__(self, url, on_connect=None, onDisconnect=None, on_message=None):
        self.url = url
        self.on_connect = on_connect
        self.on_disconnect = onDisconnect
        self.on_message = on_message
        self.ws = None
        self.running = False
        self.reconnect_delay = 3
        self.connected = False
        self.authenticated = False
        self.auth_event = threading.Event()
        self.auth_result = None
    
    def send(self, data):
        if self.ws and self.connected:
            try:
                self.ws.send(json.dumps(data))
            except Exception as e:
                logging.warning(f"WS send error: {e}")
    
    def _on_message(self, ws, message):
        try:
            msg = json.loads(message)
            t = msg.get('type', '')
            
            if t == 'auth_ok':
                self.authenticated = True
                self.auth_result = msg
                self.auth_event.set()
                if self.on_connect:
                    self.on_connect(msg)
                logging.info(f"Authenticated: {msg.get('agentId')}")
                return
            
            if t == 'auth_failed':
                self.authenticated = False
                self.auth_result = msg
                self.auth_event.set()
                logging.error(f"Auth failed: {msg.get('message')}")
                self.ws.close()
                return
            
            if not self.authenticated:
                return
            
            if self.on_message:
                self.on_message(msg)
                
        except Exception as e:
            logging.error(f"Message error: {e}")
    
    def _on_error(self, ws, error):
        logging.warning(f"WS error: {error}")
    
    def _on_close(self, ws, close_status_code=None, close_msg=None):
        self.connected = False
        self.authenticated = False
        logging.warning(f"WS closed: {close_status_code} {close_msg}")
        if self.on_disconnect:
            self.on_disconnect()
    
    def _on_open(self, ws):
        logging.info("WS connected, sending auth...")
        self.connected = True
        ws.send(json.dumps({
            'type': 'auth',
            'agentId': self.agent_id,
            'secret': self.secret,
            'hostname': self.hostname,
            'os': self.os_name
        }))
    
    def connect(self, agent_id, secret, hostname, os_name):
        self.agent_id = agent_id
        self.secret = secret
        self.hostname = hostname
        self.os_name = os_name
        
        if not WS_AVAILABLE:
            logging.error("websocket-client not installed!")
            return False
        
        from websocket import WebSocketApp
        
        while self.running:
            try:
                logging.info(f"Connecting to {self.url}...")
                self.auth_event.clear()
                self.auth_result = None
                
                self.ws = WebSocketApp(
                    self.url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
                
                # Run with ping
                self.ws.run_forever(ping_interval=25, ping_timeout=10)
                
                # Wait for auth with timeout
                auth_ok = self.auth_event.wait(timeout=10)
                
                if not auth_ok or not self.authenticated:
                    logging.warning("Auth timeout or failed, reconnecting...")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 1.5, 30)
                    continue
                
                # Reset reconnect on successful auth
                self.reconnect_delay = 3
                
            except Exception as e:
                logging.error(f"Connection error: {e}")
                time.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, 30)
        
        return True
    
    def start(self, agent_id, secret, hostname, os_name):
        self.running = True
        t = threading.Thread(target=self.connect, args=(agent_id, secret, hostname, os_name), name='WebSocketClient')
        t.start()
    
    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()

# ============================================================
# System Tray UI
# ============================================================

class SystemTray:
    def __init__(self, app):
        self.app = app
        self.hwnd = None
        self.icon_loaded = False
        self._thread = None
        self.running = False
        
        # Tray menu IDs
        self.ID_SHOW = 1001
        self.ID_STATUS = 1002
        self.ID_SEPARATOR = 1003
        self.ID_STARTUP = 1004
        self.ID_EXIT = 1005
        self.ID_CPY_ID = 1006
        self.ID_CPY_SECRET = 1007
        self.ID_OPEN_WEB = 1008
        self.ID_SEPARATOR2 = 1009
    
    def _create_tray_menu(self):
        """Create system tray menu using win32gui."""
        if not WIN32_AVAILABLE:
            return None
        
        try:
            hMenu = win32gui.CreatePopupMenu()
            
            # Status (disabled, shows current state)
            status = f"状态: {'已连接' if self.app.connected else '未连接'}"
            win32gui.AppendMenu(hMenu, 0, self.ID_STATUS, status)
            win32gui.AppendMenu(hMenu, 0, 0, '')  # separator
            
            # Agent info
            win32gui.AppendMenu(hMenu, 0, self.ID_CPY_ID, f"Agent ID: {self.app.agent_id[:8]}...")
            win32gui.AppendMenu(hMenu, 0, self.ID_CPY_SECRET, f"Secret: {self.app.secret}")
            win32gui.AppendMenu(hMenu, 0, 0, '')  # separator
            
            # Open web interface
            win32gui.AppendMenu(hMenu, 0, self.ID_OPEN_WEB, "打开控制台...")
            win32gui.AppendMenu(hMenu, 0, 0, '')  # separator
            
            # Auto-start
            auto_start = self.app.config.get('auto_start', False)
            mark = '✓ ' if auto_start else ''
            win32gui.AppendMenu(hMenu, 0, self.ID_STARTUP, f"{mark}开机自启")
            
            win32gui.AppendMenu(hMenu, 0, 0, '')  # separator
            win32gui.AppendMenu(hMenu, 0, self.ID_EXIT, "退出")
            
            return hMenu
        except Exception as e:
            logging.error(f"Menu creation error: {e}")
            return None
    
    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_COMMAND:
            cmd_id = win32api.LOWORD(wparam)
            
            if cmd_id == self.ID_EXIT:
                logging.info("User requested exit from tray menu")
                self.app.quit()
                
            elif cmd_id == self.ID_STARTUP:
                cfg = self.app.config
                auto_start = not cfg.get('auto_start', False)
                set_auto_start(auto_start)
                self.app.config['auto_start'] = auto_start
                save_config(self.app.config)
                self.refresh_menu()
                
            elif cmd_id == self.ID_CPY_ID:
                if WIN32_AVAILABLE:
                    win32clipboard.OpenClipboard()
                    win32clipboard.SetClipboardText(self.app.agent_id)
                    win32clipboard.CloseClipboard()
                    logging.info("Agent ID copied to clipboard")
                
            elif cmd_id == self.ID_CPY_SECRET:
                if WIN32_AVAILABLE:
                    win32clipboard.OpenClipboard()
                    win32clipboard.SetClipboardText(self.app.secret)
                    win32clipboard.CloseClipboard()
                    logging.info("Secret copied to clipboard")
                
            elif cmd_id == self.ID_OPEN_WEB:
                # Extract host:port from server URL
                url = self.app.server_url.replace('/agent', '')
                webbrowser.open(url)
            
        elif msg == win32con.WM_USER + 1:
            # Tray icon right-click - show context menu
            hMenu = self._create_tray_menu()
            if hMenu:
                pos = win32api.GetCursorPos()
                win32gui.SetForegroundWindow(hwnd)
                win32gui.TrackPopupMenu(hMenu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, hwnd, None)
                win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        
        elif msg == win32con.WM_DESTROY:
            win32gui.DestroyWindow(hwnd)
        
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
    
    def _register_window_class(self):
        try:
            wc = win32gui.WNDCLASS()
            wc.hInstance = win32api.GetModuleHandle(None)
            wc.lpszClassName = f"{APP_NAME}TrayClass"
            wc.lpfnWndProc = self._window_proc
            return win32gui.RegisterClass(wc)
        except Exception:
            return None
    
    def _create_icon_from_text(self):
        """Create a simple teal-colored icon programmatically."""
        try:
            # Use PIL to create a simple icon image, then convert to HICON
            size = 32
            
            if PIL_AVAILABLE:
                from PIL import Image, ImageDraw
                img = Image.new('RGBA', (size, size), (0x00, 0xd4, 0xaa, 0xFF))
                draw = ImageDraw.Draw(img)
                # Draw a white "R" 
                draw.rectangle([8, 4, 16, 28], outline='white', width=2)
                draw.line([12, 4, 12, 16], fill='white', width=2)
                draw.ellipse([12, 16, 20, 24], outline='white', width=2)
                draw.line([12, 20, 20, 28], fill='white', width=2)
                
                # Save as ICO
                ico_path = os.path.join(CONFIG_DIR, 'icon.ico')
                img.save(ico_path, format='ICO', sizes=[(size, size)])
                
                # Load the icon
                hIcon = win32gui.LoadImage(0, ico_path, win32con.IMAGE_ICON, size, size, win32con.LR_LOADFROMFILE)
                if hIcon:
                    return hIcon
        except Exception as e:
            logging.warning(f"Icon creation failed: {e}")
        
        # Fallback to system icon
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
    
    def _tray_thread(self):
        """Thread that creates the tray window."""
        if not WIN32_AVAILABLE:
            logging.error("Cannot create tray: win32gui not available")
            return
        
        try:
            pythoncom.CoInitialize()
            
            wc_name = self._register_window_class()
            
            # Create message-only window
            self.hwnd = win32gui.CreateWindowEx(
                0, wc_name, APP_NAME,
                win32con.WS_OVERLAPPED,
                0, 0, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
                0, 0, win32api.GetModuleHandle(None), None
            )
            
            # Create icon
            hIcon = self._create_icon_from_text()
            if not hIcon:
                hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            
            # Add tray icon
            nid = (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, win32con.WM_USER + 1, hIcon, APP_NAME)
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
            self.icon_loaded = True
            
            self.update_tooltip("Remote Control Agent\nNot connected")
            logging.info("System tray icon created")
            
            # Message loop using ctypes for MSG
            import ctypes
            from ctypes import wintypes
            PM_REMOVE = 0x0001
            WM_NULL = 0x0000
            
            class MSG(ctypes.Structure):
                _fields_ = [
                    ('hwnd', wintypes.HWND),
                    ('message', wintypes.UINT),
                    ('wParam', wintypes.WPARAM),
                    ('lParam', wintypes.LPARAM),
                    ('time', wintypes.DWORD),
                    ('pt', wintypes.POINT),
                ]
            
            PeekMessage = ctypes.windll.user32.PeekMessageW
            TranslateMessage = ctypes.windll.user32.TranslateMessage
            DispatchMessage = ctypes.windll.user32.DispatchMessageW
            
            msg = MSG()
            while self.running:
                if PeekMessage(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_NULL:
                        continue
                    TranslateMessage(ctypes.byref(msg))
                    DispatchMessage(ctypes.byref(msg))
                else:
                    time.sleep(0.05)
            
            # Cleanup
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
            except Exception:
                pass
            
            pythoncom.CoUninitialize()
            
        except Exception as e:
            logging.error(f"Tray thread FATAL error: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._tray_thread, name='TrayThread')
        self._thread.start()
    
    def stop(self):
        self.running = False
        if self.hwnd:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)
    
    def update_tooltip(self, text):
        """Update tray icon tooltip."""
        if not WIN32_AVAILABLE or not self.icon_loaded:
            return
        try:
            hIcon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            nid = (self.hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, win32con.WM_USER + 1, hIcon, text)
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except Exception:
            pass
    
    def refresh_menu(self):
        """Force menu refresh by sending a dummy message."""
        if self.hwnd and WIN32_AVAILABLE:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_USER + 1, 0, 0)
            except Exception:
                pass

# ============================================================
# Main Application
# ============================================================

class RemoteControlApp:
    def __init__(self):
        self.running = True
        self.connected = False
        self.authenticated = False
        self.ws_client = None
        self.screen = None
        self.tray = None
        self.agent_id = None
        self.secret = None
        self.hostname = None
        self.os_name = None
        self.server_url = None
        self.config = {}
        self.screen_thread = None
        self.stream_running = False
        self.heartbeat_running = False
    
    def init(self):
        setup_logging()
        logging.info(f"{APP_NAME} v{APP_VERSION} starting...")
        
        # Check dependencies
        missing = []
        if not WS_AVAILABLE:
            missing.append("websocket-client")
        if not (MSS_AVAILABLE or PIL_AVAILABLE):
            missing.append("mss or Pillow")
        if not PYAUTOGUI_AVAILABLE:
            missing.append("pyautogui")
        if not WIN32_AVAILABLE:
            missing.append("pywin32")
        
        if missing:
            logging.warning(f"Missing dependencies: {', '.join(missing)}")
            logging.warning("Run: pip install " + " ".join(missing))
        
        # Load config
        self.config = load_config()
        
        # Get credentials
        self.agent_id, self.secret, self.server_url = get_or_create_credentials()
        self.hostname = socket.gethostname()
        try:
            import platform
            self.os_name = f"Windows {platform.release()}"
        except Exception:
            self.os_name = "Windows"
        
        logging.info(f"Agent ID: {self.agent_id}")
        logging.info(f"Server:   {self.server_url}")
        logging.info(f"Hostname: {self.hostname}")
        
        # Init screen capture (delta-based)
        sw, sh = get_screen_size()
        self.screen = DeltaScreenCapture(sw, sh)
        
        # Init tray (optional - don't crash if it fails)
        try:
            self.tray = SystemTray(self)
            self.tray.start()
            logging.info("System tray started")
        except Exception as e:
            logging.warning(f"System tray failed to start (non-critical): {e}")
            self.tray = None
        
        # Init WebSocket client
        self.ws_client = WebSocketClient(
            url=self.server_url,
            on_connect=self._on_connect,
            onDisconnect=self._on_disconnect,
            on_message=self._on_message
        )
        
        logging.info("Initialization complete")
        self._print_connect_info()
    
    def _print_connect_info(self):
        # Extract web URL from server URL
        web_url = self.server_url.replace('/agent', '')
        info = f"""
================================================================
       Remote Control Agent v{APP_VERSION}
================================================================
  Agent ID:   {self.agent_id}
  Secret:     {self.secret}
  Server:     {self.server_url}
  Web Console: {web_url}
================================================================
  How to connect:
    1. Open browser: {web_url}
    2. Server password: WeiChao_2026Ctrl!
    3. Enter Agent ID above
================================================================
  Agent is minimized to system tray.
  Right-click tray icon for menu.
================================================================
"""
        print(info)
    
    def _on_connect(self, msg):
        self.connected = True
        self.authenticated = True
        if self.tray:
            self.tray.update_tooltip(f"Remote Control Agent\n已连接: {msg.get('agentId','')[:8]}")
        self._start_screen_stream()
        self._start_heartbeat()
        logging.info("Connected and authenticated!")
    
    def _on_disconnect(self):
        self.connected = False
        self.authenticated = False
        self._stop_screen_stream()
        if self.tray:
            self.tray.update_tooltip("Remote Control Agent\n未连接")
        logging.warning("Disconnected")
    
    def _on_message(self, msg):
        t = msg.get('type', '')
        
        if t == 'mouse':
            handle_mouse(msg.get('x', 0), msg.get('y', 0), msg.get('button', 'left'), msg.get('action', 'move'))
        
        elif t == 'key':
            handle_key(msg.get('key', ''), msg.get('action', 'press'))
        
        elif t == 'exec':
            cmd = msg.get('cmd', '')
            session = msg.get('session', '')
            threading.Thread(target=execute_command, args=(cmd, session, self.ws_client.send), daemon=True).start()
        
        elif t == 'file_request':
            action = msg.get('action', '')
            session = msg.get('session', '')
            if action == 'download':
                path = msg.get('path', '')
                filename = msg.get('filename', '')
                threading.Thread(target=handle_file_download, args=(path, session, filename, self.ws_client.send), daemon=True).start()
    
    def _start_screen_stream(self):
        if self.stream_running:
            return
        self.stream_running = True
        
        def stream_loop():
            logging.info("Screen streaming started (delta mode)")
            while self.stream_running and self.authenticated:
                try:
                    msg = self.screen.capture_and_encode()
                    if msg:
                        self.ws_client.send(msg)
                except Exception as e:
                    logging.warning(f"Stream error: {e}")
                time.sleep(1.0 / SCREEN_FPS)
            logging.info("Screen streaming stopped")
        
        self.screen_thread = threading.Thread(target=stream_loop, name='ScreenStream')
        self.screen_thread.start()
    
    def _stop_screen_stream(self):
        self.stream_running = False

    def _start_heartbeat(self):
        """Send application-level heartbeat to keep agent alive on server."""
        if self.heartbeat_running:
            return
        self.heartbeat_running = True

        def heartbeat_loop():
            while self.heartbeat_running and self.authenticated:
                try:
                    self.ws_client.send({'type': 'pong'})
                except Exception as e:
                    logging.debug(f"WS heartbeat skipped: {e}")
                try:
                    server_base = self.server_url.rsplit('/agent', 1)[0]
                    ping_url = f"{server_base}/api/agent/ping?agentId={self.agent_id}"
                    req = urllib.request.Request(ping_url, headers={'User-Agent': 'RemoteControlAgent/1.0'})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        logging.debug(f"HTTP heartbeat ok: {resp.status}")
                except Exception as e:
                    logging.debug(f"HTTP heartbeat skipped: {e}")
                time.sleep(30)

        t = threading.Thread(target=heartbeat_loop, name='Heartbeat', daemon=True)
        t.start()

    def _stop_heartbeat(self):
        self.heartbeat_running = False
    
    def run(self):
        """Start the application."""
        self.init()
        
        # Start WebSocket connection
        self.ws_client.start(self.agent_id, self.secret, self.hostname, self.os_name)
        
        # Main loop (keep main thread alive)
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logging.error(f"Main loop error: {e}")
        
        self.quit()

    def quit(self):
        logging.info('Shutting down...')
        self.running = False
        self._stop_screen_stream()
        if self.ws_client:
            self.ws_client.stop()
        if self.tray:
            self.tray.stop()
        logging.info('Shutdown complete')
        sys.exit(0)


# ============================================================
# Entry Point
# ============================================================

if __name__ == '__main__':
    # Single instance check using file lock
    lock_file = os.path.join(CONFIG_DIR, 'agent.lock')
    lock_fd = None
    try:
        lock_fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode())
    except FileExistsError:
        print(f'{APP_NAME} is already running! (another instance is active)')
        sys.exit(0)
    except Exception as e:
        pass  # Lock file failed, just continue
    
    app = RemoteControlApp()
    app.run()
    
    # Cleanup
    if lock_fd is not None:
        try: os.close(lock_fd)
        except: pass
        try: os.unlink(lock_file)
        except: pass

