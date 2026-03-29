#!/usr/bin/env python3
"""Android CLI - 类似 agent-browser 的命令行工具"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adb_client import ADBClient
from src.snapshot import Snapshoter
from src.element import find_element, print_elements


class AndroidCLI:
    def __init__(self, device_id: str = None):
        self.adb = ADBClient(device_id)
        self.snapshoter = Snapshoter(self.adb)
        self.current_snapshot = None
        self.last_screen = None

    def snapshot(self) -> dict:
        """获取快照并返回元素树"""
        snap = self.snapshoter.take()
        self.current_snapshot = snap
        self.last_screen = snap.screen_path

        print(f"\n=== Snapshot ===")
        print(f"Screen: {snap.screen_path}")
        print(f"Size: {snap.width}x{snap.height}")
        print(f"Elements: {len(snap.elements)}")
        print()
        print_elements(snap.elements)

        return {"screen": snap.screen_path, "elements": snap.elements}

    def screenshot(self, path: str = None) -> str:
        """保存截图"""
        if not path:
            path = f"screenshot_{int(time.time())}.png"
        return self.adb.screenshot(path)

    def click(self, selector: str) -> dict:
        """点击元素或坐标"""
        # 纯数字坐标 "x,y" 格式
        if "," in selector:
            parts = selector.split(",")
            if len(parts) == 2:
                a, b = parts[0].strip(), parts[1].strip()
                if (a.replace("-", "").isdigit() and b.replace("-", "").isdigit()):
                    x, y = int(a), int(b)
                    self.adb.click(x, y)
                    print(f"[OK] Clicked at ({x}, {y})")
                    time.sleep(0.5)
                    return {"x": x, "y": y}

        # 按元素
        if not self.current_snapshot:
            self.snapshot()

        elements = self.current_snapshot.elements

        if selector.startswith("ref="):
            ref = selector.split("=")[1]
            el = next((e for e in elements if e.ref == ref), None)
        elif selector.startswith("text="):
            text = selector.split("=", 1)[1]
            el = find_element(elements, text=text)
        elif ":" in selector:
            prefix, value = selector.split(":", 1)
            if prefix == "text":
                el = find_element(elements, text=value)
            elif prefix == "textcontains":
                el = find_element(elements, text_contains=value)
            else:
                raise ValueError(f"未知 selector: {selector}")
        else:
            el = find_element(elements, text_contains=selector)

        if not el:
            raise ValueError(f"未找到元素: {selector}")

        cx, cy = el.center
        self.adb.click(cx, cy)
        print(f"[OK] Clicked [{el.ref}] at ({cx}, {cy})")
        time.sleep(0.5)
        return {"ref": el.ref, "x": cx, "y": cy}

    def type(self, selector: str, text: str) -> dict:
        """输入文字"""
        if not self.current_snapshot:
            self.snapshot()

        elements = self.current_snapshot.elements

        if selector.startswith("ref="):
            ref = selector.split("=")[1]
            el = next((e for e in elements if e.ref == ref), None)
        else:
            el = find_element(elements, text_contains=selector)

        if not el:
            raise ValueError(f"未找到元素: {selector}")

        cx, cy = el.center
        self.adb.click(cx, cy)
        time.sleep(0.3)
        self.adb.input_text(text)
        print(f"[OK] Typed '{text}' at [{el.ref}]")
        return {"ref": el.ref, "text": text}

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300):
        """滑动"""
        self.adb.swipe(x1, y1, x2, y2, duration)
        print(f"[OK] Swiped ({x1},{y1}) -> ({x2},{y2})")
        time.sleep(0.3)

    def wait(self, ms: int):
        """等待"""
        time.sleep(ms / 1000)
        print(f"[OK] Waited {ms}ms")

    def press(self, key: str) -> dict:
        """按键"""
        KEY_MAP = {"back": 4, "home": 3, "menu": 82, "enter": 66, "delete": 67}
        keycode = KEY_MAP.get(key.lower())
        if not keycode:
            raise ValueError(f"未知按键: {key}，可用: {list(KEY_MAP.keys())}")

        self.adb.press_key(keycode)
        print(f"[OK] Pressed {key}")
        time.sleep(0.3)
        return {"key": key}


def main():
    parser = argparse.ArgumentParser(description="Android CLI")
    parser.add_argument("command", help="命令")
    parser.add_argument("args", nargs="*", help="命令参数")
    parser.add_argument("--device", "-d", help="设备 ID")

    args = parser.parse_args()

    cli = AndroidCLI(device_id=args.device)

    try:
        if args.command == "snapshot" or args.command == "s":
            cli.snapshot()

        elif args.command == "click" or args.command == "c":
            if not args.args:
                print("Usage: click <selector>")
                sys.exit(1)
            cli.click(args.args[0])

        elif args.command == "type" or args.command == "t":
            if len(args.args) < 2:
                print("Usage: type <selector> <text>")
                sys.exit(1)
            cli.type(args.args[0], args.args[1])

        elif args.command == "swipe":
            if len(args.args) < 4:
                print("Usage: swipe <x1> <y1> <x2> <y2> [duration]")
                sys.exit(1)
            duration = int(args.args[4]) if len(args.args) > 4 else 300
            cli.swipe(
                int(args.args[0]),
                int(args.args[1]),
                int(args.args[2]),
                int(args.args[3]),
                duration,
            )

        elif args.command == "wait":
            if not args.args:
                print("Usage: wait <ms>")
                sys.exit(1)
            cli.wait(int(args.args[0]))

        elif args.command == "press":
            if not args.args:
                print("Usage: press <key>")
                sys.exit(1)
            cli.press(args.args[0])

        elif args.command == "screenshot":
            path = args.args[0] if args.args else None
            cli.screenshot(path)

        else:
            print(f"未知命令: {args.command}")
            sys.exit(1)

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
