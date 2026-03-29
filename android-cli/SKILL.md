# Android 自动化 CLI (agent-android)

类似 agent-browser 的命令行工具，用于 Android 应用自动化。

## 环境要求

- ADB (Android Debug Bridge) - 已安装
- Python 3.10+
- Android 设备开启 USB 调试

## 安装

```bash
# ADB 已通过 winget 安装，位于：
# C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe

# 安装 Python 依赖
pip install -r requirements.txt
```

## 使用方法

```bash
python -m src.cli <command> [args]
```

## 命令

### snapshot, s
获取当前页面截图 + UI 元素树

### click <selector>
点击元素
- `click "发布"` - 按 text 模糊匹配
- `click "text:发布笔记"` - 按 text 精确匹配
- `click "textcontains:发布"` - text 包含匹配
- `click "ref=e5"` - 按 ref 编号

### type <selector> <text>
输入文字（英文/数字）

### swipe <x1> <y1> <x2> <y2> [duration]
滑动，从 (x1,y1) 到 (x2,y2)

### press <key>
按键
- `back` - 返回键
- `home` - Home键
- `menu` - 菜单键
- `enter` - 确认键

### screenshot [path]
保存截图到指定路径

### wait <ms>
等待（毫秒）

## 示例

```bash
# 获取快照
python -m src.cli snapshot

# 点击发布按钮
python -m src.cli click "发布"

# 输入标题
python -m src.cli type "ref=e10" "我的测试标题"

# 等待2秒
python -m src.cli wait 2000

# 返回上一页
python -m src.cli press back

# 向上滑动
python -m src.cli swipe 540 1200 540 400
```

## ADB 连接状态

设备状态说明：
- `device` - 正常连接，已授权
- `unauthorized` - 需要在手机上点击"允许USB调试"
- `offline` - 连接断开

## 已知限制

- 中文输入需要通过剪贴板方式（待实现）
- WebView 内部元素需要通过 Appium context 切换（待实现）
