#!/usr/bin/env python3
"""小红书 App 自动化操作"""

import subprocess
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adb_client import ADBClient
from src.snapshot import Snapshoter
from src.element import find_element, print_elements
from src.wait import Waiter
from src.state import StateMachine, PageState

ADB_PATH = r"C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe"
DEVICE_ID = "A6DA6LI7YTFEEYJV"


class XHSOperator:
    """小红书自动化操作类"""

    APP_PACKAGE = "com.xingin.xhs"
    APP_ACTIVITY = ".index.v2.IndexActivityV2"

    def __init__(self, device_id: str = None):
        self.device_id = device_id or DEVICE_ID
        self.adb = ADBClient(self.device_id)
        self.snapshoter = Snapshoter(self.adb)
        self.waiter = Waiter(self.adb, self.snapshoter)
        self.state = StateMachine()

    def launch(self) -> bool:
        """启动小红书 App"""
        print(f"[OK] 启动小红书...")
        code, out, err = self.adb._run(
            f"shell am start -n {self.APP_PACKAGE}/{self.APP_ACTIVITY}"
        )
        time.sleep(3)

        # 检测 Activity
        activity = self.adb.current_activity()
        self.state.current_state = self.state.detect(activity)
        print(f"[OK] 当前页面: {self.state.current_state.value} ({activity})")
        return code == 0

    def snapshot(self, show: bool = True) -> dict:
        """拍快照"""
        snap = self.snapshoter.take()
        if show:
            print(f"\n=== Snapshot ({snap.width}x{snap.height}) ===")
            print_elements(snap.elements)

        # 更新状态
        activity = self.adb.current_activity()
        self.state.current_state = self.state.detect(activity)

        return {"screen": snap.screen_path, "elements": snap.elements, "activity": activity}

    def click_element(self, text_contains: str = None, ref: str = None, index: int = 0) -> bool:
        """点击元素"""
        snap = self.snapshoter.take()
        elements = snap.elements

        if ref:
            el = next((e for e in elements if e.ref == ref), None)
        elif text_contains:
            el = find_element(elements, text_contains=text_contains, index=index)
        else:
            raise ValueError("需要提供 text_contains 或 ref")

        if not el:
            print(f"[ERROR] 未找到元素: {text_contains or ref}")
            return False

        cx, cy = el.center
        self.adb.click(cx, cy)
        print(f"[OK] 点击 [{el.ref}] at ({cx}, {cy})")
        time.sleep(0.5)
        return True

    def wait_and_click(self, text_contains: str, timeout_ms: int = 5000) -> bool:
        """等待元素出现并点击"""
        el = self.waiter.for_element(text_contains=text_contains, timeout_ms=timeout_ms)
        if el:
            cx, cy = el.center
            self.adb.click(cx, cy)
            print(f"[OK] 点击 [{el.ref}] at ({cx}, {cy})")
            return True
        print(f"[ERROR] 等待元素超时: {text_contains}")
        return False

    def scroll_down(self, duration: int = 300):
        """向下滑动（浏览内容）"""
        snap = self.snapshoter.take()
        cx = snap.width // 2
        y1 = int(snap.height * 0.7)
        y2 = int(snap.height * 0.3)
        self.adb.swipe(cx, y1, cx, y2, duration)
        print(f"[OK] 滑动 ({cx},{y1}) -> ({cx},{y2})")
        time.sleep(0.3)

    def go_to_profile(self) -> bool:
        """导航到个人主页"""
        print("[OK] 导航到个人主页...")

        # 尝试点击底部"我的"标签
        snap = self.snapshoter.take()
        for e in snap.elements:
            if e.content_desc and ("我的" in e.content_desc or "profile" in e.content_desc.lower()):
                cx, cy = e.center
                self.adb.click(cx, cy)
                print(f"[OK] 点击我的标签")
                time.sleep(2)
                return True

        # 如果找不到，尝试点击右下角区域（通常是个人页入口）
        self.adb.click(int(snap.width * 0.9), int(snap.height * 0.95))
        print(f"[OK] 点击右下角")
        time.sleep(2)
        return True

    def go_home(self) -> bool:
        """返回首页"""
        print("[OK] 返回首页...")
        self.adb.press_key(4)  # back
        time.sleep(1)
        self.adb.press_key(4)  # back
        time.sleep(1)
        return True


def main():
    """测试入口"""
    op = XHSOperator()

    print("=== 小红书自动化测试 ===")
    print(f"设备: {op.device_id}")

    # 启动 App
    op.launch()

    # 拍快照
    op.snapshot()

    # 等待并点击"我的"标签
    # op.wait_and_click("我的", timeout_ms=3000)


if __name__ == "__main__":
    main()
