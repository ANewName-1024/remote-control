#!/usr/bin/env python3
"""ADB 连接管理器"""

import subprocess
import time
import threading
from dataclasses import dataclass
from typing import Optional

ADB_PATH = r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe"


@dataclass
class ADBDevice:
    device_id: str
    state: str  # device, unauthorized, offline


class ADBClient:
    HEARTBEAT_INTERVAL = 30
    RECONNECT_RETRIES = 3
    RECONNECT_INTERVAL = 2

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        self._lock = threading.Lock()
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def _run(self, cmd: str, timeout: int = 10) -> tuple[int, str, str]:
        """执行 ADB 命令"""
        full_cmd = f'"{ADB_PATH}" '
        if self.device_id:
            full_cmd += f"-s {self.device_id} "
        full_cmd += cmd
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    def _get_default_device(self) -> str:
        """获取默认设备"""
        code, out, _ = self._run("devices")
        lines = [l.strip() for l in out.split("\n") if l.strip() and "\t" in l]
        if not lines:
            raise RuntimeError("未检测到 Android 设备，请检查 USB 调试是否开启")
        first = lines[0].split("\t")[0]
        return first

    def ensure_connected(self) -> bool:
        """确保设备连接，自动重连"""
        if not self.device_id:
            self.device_id = self._get_default_device()

        for attempt in range(self.RECONNECT_RETRIES):
            code, _, err = self._run("shell echo alive")
            if code == 0:
                return True
            self._run(f"connect {self.device_id}:5555")
            time.sleep(self.RECONNECT_INTERVAL)
        raise ConnectionError(f"ADB 连接失败，已重试 {self.RECONNECT_RETRIES} 次")

    def start_heartbeat(self):
        """启动心跳保活线程"""
        def heartbeat():
            while not self._stop_heartbeat.is_set():
                time.sleep(self.HEARTBEAT_INTERVAL)
                try:
                    self.ensure_connected()
                except:
                    pass

        self._heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """停止心跳"""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

    def screenshot(self, local_path: str = "screen.png") -> str:
        """截图并拉取到本地"""
        self.ensure_connected()
        remote_path = "/sdcard/screen.png"
        self._run(f"shell screencap -p {remote_path}")
        self._run(f"pull {remote_path} {local_path}")
        return local_path

    def dump_ui(self, local_path: str = "ui.xml") -> str:
        """dump UI 层级并拉取到本地"""
        self.ensure_connected()
        remote_path = "/sdcard/ui.xml"
        self._run(f"shell uiautomator dump {remote_path}")
        self._run(f"pull {remote_path} {local_path}")
        return local_path

    def click(self, x: int, y: int):
        """点击坐标"""
        self.ensure_connected()
        self._run(f"shell input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动"""
        self.ensure_connected()
        self._run(f"shell input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def input_text(self, text: str):
        """输入文字（英文/数字）"""
        self.ensure_connected()
        text = text.replace(" ", "%s").replace("'", "\\'")
        self._run(f"shell input text '{text}'")

    def press_key(self, keycode: int):
        """按键（如 4=返回，82=菜单）"""
        self.ensure_connected()
        self._run(f"shell input keyevent {keycode}")

    def current_activity(self) -> str:
        """获取当前 Activity"""
        self.ensure_connected()
        _, out, _ = self._run(
            "shell dumpsys activity activities | grep mResumedActivity"
        )
        if "mResumedActivity" in out:
            return (
                out.split("mResumedActivity=")[1]
                .split()[0]
                .split("/")[-1]
                .rstrip("}")
            )
        return ""
