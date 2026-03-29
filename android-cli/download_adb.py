#!/usr/bin/env python3
"""下载 Android Platform Tools - 使用阿里云镜像"""

import urllib.request
import ssl
import os

def download(url, output_path):
    print(f"正在下载: {url}")
    
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
    # 尝试阿里云镜像
    mirrors = [
        "https://mirrors.aliyun.com/android-platform-tools/latest/platform-tools-windows.zip",
        "https://mirrors.tencent.com/android-platform-tools/latest/platform-tools-windows.zip",
    ]
    
    output = "D:/android-cli/platform-tools.zip"
    
    for mirror in mirrors:
        print(f"尝试镜像: {mirror}")
        if download(mirror, output):
            break
