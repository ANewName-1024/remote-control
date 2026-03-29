#!/usr/bin/env python3
"""并行截图 + UI dump"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.element import parse_elements


@dataclass
class Snapshot:
    screen_path: str
    xml_path: str
    width: int
    height: int
    elements: list
    timestamp: float


class Snapshoter:
    def __init__(self, adb_client):
        self.adb = adb_client
        self._executor = ThreadPoolExecutor(max_workers=4)

    def take(
        self, screen_path: str = "screen.png", xml_path: str = "ui.xml"
    ) -> Snapshot:
        """同步方式获取快照"""
        screen_future = self._executor.submit(self.adb.screenshot, screen_path)
        xml_future = self._executor.submit(self.adb.dump_ui, xml_path)

        screen_path = screen_future.result()
        xml_path = xml_future.result()

        code, out, _ = self.adb._run("shell wm size")
        if code == 0 and "Physical size:" in out:
            size = out.split(":")[1].strip()
            width, height = map(int, size.split("x"))
        else:
            width, height = 1080, 1920

        elements = parse_elements(xml_path)

        return Snapshot(
            screen_path=screen_path,
            xml_path=xml_path,
            width=width,
            height=height,
            elements=elements,
            timestamp=time.time(),
        )
