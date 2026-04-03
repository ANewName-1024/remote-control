#!/usr/bin/env python3
"""智能等待 + 指数退避"""

import time
from typing import Optional

from src.element import find_element, UIElement


class Waiter:
    """智能等待器，支持指数退避"""

    def __init__(self, adb_client, snapshoter):
        self.adb = adb_client
        self.snapshoter = snapshoter

    def for_element(
        self,
        text: Optional[str] = None,
        text_contains: Optional[str] = None,
        resource_id: Optional[str] = None,
        timeout_ms: int = 5000,
        interval_base_ms: int = 200,
    ) -> Optional[UIElement]:
        """
        等待元素出现

        Args:
            text: 精确匹配 text
            text_contains: 模糊匹配 text
            resource_id: 匹配 resource-id
            timeout_ms: 超时时间（毫秒）
            interval_base_ms: 初始间隔（毫秒），会指数增长

        Returns:
            找到的元素，或 None
        """
        timeout_sec = timeout_ms / 1000
        start = time.time()
        interval = interval_base_ms / 1000
        max_interval = 2.0

        while time.time() - start < timeout_sec:
            snap = self.snapshoter.take()
            el = find_element(
                snap.elements,
                text=text,
                text_contains=text_contains,
                resource_id=resource_id,
            )

            if el:
                return el

            time.sleep(interval)
            interval = min(interval * 1.5, max_interval)

        return None

    def for_activity(self, activity_name: str, timeout_ms: int = 5000) -> bool:
        """等待到达指定 Activity"""
        timeout_sec = timeout_ms / 1000
        start = time.time()

        while time.time() - start < timeout_sec:
            current = self.adb.current_activity()
            if activity_name in current:
                return True
            time.sleep(0.5)

        return False

    def for_text_change(self, old_text: str, timeout_ms: int = 5000) -> bool:
        """等待指定元素的文本发生变化"""
        timeout_sec = timeout_ms / 1000
        start = time.time()

        while time.time() - start < timeout_sec:
            snap = self.snapshoter.take()
            el = find_element(snap.elements, text_contains=old_text)
            if not el:
                # 文本已消失，说明发生了变化
                return True
            time.sleep(0.3)

        return False
