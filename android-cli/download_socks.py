#!/usr/bin/env python3
"""通过 SOCKS 代理下载 Android Platform Tools"""

import urllib.request
import ssl
import os
import socks
import socket

def download_via_socks():
    url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
    output_path = "D:/android-cli/platform-tools.zip"
    
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
    download_via_socks()
