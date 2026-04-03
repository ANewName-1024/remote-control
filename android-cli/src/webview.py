#!/usr/bin/env python3
"""Appium WebView 桥接 - 处理小红书等复杂 App 的 WebView 内容"""

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.webdriver import WebDriver
from typing import Optional

APPIUM_SERVER = "http://127.0.0.1:4723"

# 小红书 App 配置
XHS_CAPS = {
    "platformName": "Android",
    "deviceName": "Android Device",
    "appPackage": "com.xingin.xhs",
    "appActivity": ".index.v2.IndexActivityV2",
    "noReset": True,
    "autoGrantPermissions": True,
    "automationName": "UiAutomator2",
    "uiautomator2ServerInstallTimeout": 60000,
    "disableWindowAnimation": True,
    "skipServerInstallation": False,
    "adbPort": 5037,  # 默认 ADB 端口
}


class WebViewBridge:
    """Appium WebView 桥接，用于访问 App 内的 WebView 内容"""

    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.current_context: Optional[str] = None

    def connect(self) -> bool:
        """连接到 Appium Server 并启动小红书"""
        try:
            options = UiAutomator2Options().load_capabilities(XHS_CAPS)
            self.driver = webdriver.Remote(APPIUM_SERVER, options=options)
            self.driver.implicitly_wait(10)
            print("[OK] Appium 连接成功")
            return True
        except Exception as e:
            print(f"[ERROR] Appium 连接失败: {e}")
            return False

    def get_contexts(self) -> list:
        """获取所有可用上下文"""
        if not self.driver:
            return []
        return self.driver.contexts

    def switch_to_webview(self) -> bool:
        """切换到 WebView 上下文"""
        if not self.driver:
            return False

        contexts = self.get_contexts()
        print(f"[OK] 可用上下文: {contexts}")

        # 找到 WebView 上下文
        webview_name = None
        for ctx in contexts:
            if "WEBVIEW" in ctx or "PLUGIN" in ctx:
                webview_name = ctx
                break

        if webview_name:
            self.driver.switch_to.context(webview_name)
            self.current_context = webview_name
            print(f"[OK] 已切换到: {webview_name}")
            return True
        else:
            print("[ERROR] 未找到 WebView 上下文")
            return False

    def switch_to_native(self) -> bool:
        """切换回 Native 上下文"""
        if not self.driver:
            return False

        self.driver.switch_to.context("NATIVE_APP")
        self.current_context = "NATIVE_APP"
        print("[OK] 已切换回 Native")
        return True

    def get_webview_url(self) -> Optional[str]:
        """获取当前 WebView 的 URL（如果可获取）"""
        if not self.driver:
            return None
        try:
            return self.driver.current_url
        except:
            return None

    def find_web_element(self, selector: str) -> Optional:
        """在 WebView 内用 CSS selector 查找元素"""
        if not self.driver:
            return None

        try:
            # 支持 CSS selector
            return self.driver.find_element("css selector", selector)
        except Exception as e:
            print(f"[ERROR] 查找元素失败: {e}")
            return None

    def click_web_element(self, selector: str) -> bool:
        """点击 WebView 内的元素"""
        el = self.find_web_element(selector)
        if el:
            el.click()
            return True
        return False

    def quit(self):
        """关闭连接"""
        if self.driver:
            self.driver.quit()
            print("[OK] Appium 连接已关闭")


def test_connection():
    """测试 Appium 连接"""
    bridge = WebViewBridge()
    if bridge.connect():
        contexts = bridge.get_contexts()
        print(f"上下文列表: {contexts}")
        bridge.quit()
        return True
    return False


if __name__ == "__main__":
    test_connection()
