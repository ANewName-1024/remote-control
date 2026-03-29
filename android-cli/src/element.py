#!/usr/bin/env python3
"""XML 解析为带 ref 的元素列表"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

_ref_counter = 0


@dataclass
class UIElement:
    ref: str
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    bounds: tuple
    clickable: bool
    enabled: bool
    focusable: bool

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def is_displayed(self) -> bool:
        x1, y1, x2, y2 = self.bounds
        return x2 > x1 and y2 > y1


def _generate_ref() -> str:
    global _ref_counter
    _ref_counter += 1
    return f"e{_ref_counter}"


def parse_elements(xml_path: str) -> list[UIElement]:
    global _ref_counter
    _ref_counter = 0

    if not xml_path or not __import__("os").path.exists(xml_path):
        return []

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return []

    elements = []

    def parse_node(node: ET.Element):
        global _ref_counter
        text = node.get("text", "") or ""
        content_desc = node.get("content-desc", "") or ""
        resource_id = node.get("resource-id", "") or ""
        class_name = node.get("class", "") or ""
        bounds_str = node.get("bounds", "")

        bounds = (0, 0, 0, 0)
        if bounds_str:
            coords = bounds_str.replace("[", "").replace("]", "").split(",")
            if len(coords) == 4:
                bounds = tuple(int(c) for c in coords)

        clickable = node.get("clickable", "false") == "true"
        enabled = node.get("enabled", "true") == "true"
        focusable = node.get("focusable", "false") == "true"

        ref = _generate_ref()

        element = UIElement(
            ref=ref,
            text=text,
            content_desc=content_desc,
            resource_id=resource_id,
            class_name=class_name,
            bounds=bounds,
            clickable=clickable,
            enabled=enabled,
            focusable=focusable,
        )

        for child in node:
            elements.append(element)
            parse_node(child)

    for child in root:
        parse_node(child)

    return elements


def find_element(
    elements: list[UIElement],
    text: Optional[str] = None,
    text_contains: Optional[str] = None,
    resource_id: Optional[str] = None,
    class_name: Optional[str] = None,
    clickable: Optional[bool] = None,
    index: int = 0,
) -> Optional[UIElement]:
    candidates = elements

    if text:
        candidates = [e for e in candidates if e.text == text]
    elif text_contains:
        candidates = [e for e in candidates if text_contains in (e.text or "")]

    if resource_id:
        candidates = [e for e in candidates if e.resource_id == resource_id]

    if class_name:
        candidates = [e for e in candidates if class_name in e.class_name]

    if clickable is not None:
        candidates = [e for e in candidates if e.clickable == clickable]

    candidates = [e for e in candidates if e.is_displayed]

    if index < len(candidates):
        return candidates[index]
    return None


def print_elements(elements: list[UIElement], limit: int = 50):
    for i, e in enumerate(elements[:limit]):
        clickable_flag = "✓" if e.clickable else " "
        bounds_str = f"[{e.bounds[0]},{e.bounds[1]}][{e.bounds[2]},{e.bounds[3]}]"
        text_display = (e.text[:20] + "...") if len(e.text) > 20 else e.text
        print(f"[{e.ref}] {clickable_flag} {bounds_str} | {e.class_name} | {text_display}")

    if len(elements) > limit:
        print(f"... 还有 {len(elements) - limit} 个元素")
