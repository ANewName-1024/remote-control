#!/usr/bin/env python3
"""通过 SOCKS 代理下载 Android Platform Tools"""

import urllib.request
import ssl
import os
import socks
import socket

def download(url, output_path):
    print(f"正在下载: {url}")
    print("使用 SOCKS 代理: 127.0.0.1:7890")
    
    # 设置 SOCKS 代理
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
    socket.socket = socks.socksocket
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        urllib.request.urlretrieve(url, output_path)
        size = os.path.getsize(output_path)
        print(f"下载完成: {size} bytes ({size/1024/1024:.1f} MB)")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False

if __name__ == "__main__":
    # 尝试多个源
    sources = [
        ("https://dl.google.com/android/repository/platform-tools-latest-windows.zip", "D:/android-cli/platform-tools.zip"),
        ("https://mirrors.aliyun.com/android-platform-tools/latest/platform-tools-windows.zip", "D:/android-cli/platform-tools.zip"),
    ]
    
    for url, path in sources:
        print(f"\n尝试: {url}")
        if download(url, path):
            break
