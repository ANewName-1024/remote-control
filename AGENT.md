# Agent 使用说明 - 远程控制系统

> 本文件供 AI Agent 阅读，帮助快速理解、修改和调试本仓库代码。

---

## 一、项目概述

**功能：** 从浏览器（安卓/PC）远程控制 Windows 电脑，无需端口映射，Agent 主动连接云服务器。

**三组件架构：**
```
移动端浏览器 ──HTTPS/WSS──► VPS Node.js 中继 ──WS──► Windows Python Agent
                                         │
                                    Web 控制台
                                    (static/)
```

**Agent ID 和 Secret 认证方式** — 每次连接需要输入 Agent 分配的 UUID 和密钥。

---

## 二、关键文件说明

### 2.1 服务器端 `server/`

| 文件 | 作用 | 关键点 |
|------|------|--------|
| `index.js` | Node.js WebSocket 中继主入口 | 路由 agent ↔ client 消息；静态文件服务；文件上传接口 |
| `static/index.html` | **Web 控制台**（桌面端） | 原生 HTML+JS，非 Flutter |
| `package.json` | 依赖 | `ws`、`express`、`multer` |

**服务器端口：** 默认 `21112`，由环境变量 `PORT` 控制。
**访问密码：** 环境变量 `ACCESS_PASSWORD`。
**静态文件：** `static/` 目录通过 `express.static` 提供服务。

### 2.2 Windows Agent `agent/`

| 文件 | 作用 | 关键点 |
|------|------|--------|
| `agent.py` | Python 主程序 | 屏幕捕获、输入模拟、WebSocket 客户端 |
| `requirements.txt` | 依赖 | `pyautogui`（输入）、`Pillow`（截图）、`websockets` |

**Python 版本：** 3.8+
**关键全局变量：**
- `_held_button` — 跟踪当前按住的鼠标按钮（`'left'`/`'right'`），用于 drag 支持
- `handle_mouse()` — 鼠标事件处理，`move` 时若有 `_held_button` 则用 `pyautogui.drag()` 而非 `moveTo()`
- `handle_key()` — 键盘事件，区分 `down`/`up`/`press`

**屏幕捕获方式：** `Pillow.ImageGrab`（截取全屏）→ JPEG 编码 → 通过 WebSocket 发送。
**屏幕分辨率：** 启动时通过 `ctypes` 调用 Windows API 获取实际分辨率。
**鼠标事件：** 通过 `pyautogui` 模拟，支持 click/drag/scroll。

### 2.3 Flutter 移动端 `remote_control_app/`（独立仓库）

位于 `D:\.openclaw\workspace\remote_control_app/`。

---

## 三、消息协议

### 3.1 客户端 → 服务器

```json
{ "type": "mouse", "action": "down|up|move|click|scroll", "x": 100, "y": 200, "button": "left|right", "buttons": 1 }
{ "type": "key", "action": "down|up|press", "key": "a" }
{ "type": "clipboard", "action": "get|set", "content": "..." }
{ "type": "file_request", "action": "download|upload", "path": "C:/Users/..." }
{ "type": "agent", "action": "subscribe|unsubscribe", "agentId": "uuid" }
```

### 3.2 服务器 → 客户端

```json
{ "type": "screen", "fmt": "jpeg", "data": "<base64>", "w": 1920, "h": 1080 }
{ "type": "screen", "fmt": "jpeg", "data": "<base64>", "w": 1920, "h": 1080, "region": [x,y,w,h] }
{ "type": "clipboard", "content": "..." }
{ "type": "file_chunk", "session": "uuid", "chunk": "<base64>", "done": false }
```

---

## 四、构建与部署

### 4.1 服务器部署（VPS）

```bash
cd remote-control/server
npm install
ACCESS_PASSWORD=xxx PORT=21112 node index.js
# 或通过 pm2
pm2 start index.js --name remote-control --env ACCESS_PASSWORD=xxx
```

**重启后自动恢复：**
```bash
pm2 startup  # 生成 systemd init 脚本
pm2 save     # 保存当前进程列表
```

### 4.2 Windows Agent 部署

```powershell
cd remote-control/agent
pip install -r requirements.txt
# 设置服务器地址
$env:RC_SERVER = "ws://8.137.116.121:21112"
python agent.py
```

**打包为 exe（可选）：**
```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole --name RemoteControlAgent agent.py
```

### 4.3 Flutter 移动端构建

```bash
# 清理
flutter clean

# Release 构建（推荐，Flutter 3.24 + android-arm64）
flutter build apk --release --target-platform android-arm64

# 输出
# build/app/outputs/flutter-apk/app-release.apk
```

**构建注意事项：**
- Flutter SDK：`D:\flutter-3.24`（稳定版，3.41.6 太新导致 Maven artifacts 缺失）
- 需要 `android-arm64` target（手机通常是这个架构）
- Gradle 离线构建：`--offline` 在有缓存时可用

---

## 五、修改指南

### 5.1 添加新的鼠标按钮（如中键）

**Agent 端：** `agent.py` 的 `handle_mouse()` 中，`button` 参数增加 `'middle'` 分支，对应 `pyautogui.mouseDown(button='middle')`。

**移动端：** `touch_handler.dart` 的 `_mapButtonsToString()` 中添加对应的位标记映射。

### 5.2 添加新的键盘快捷键

**Agent 端：** `agent.py` 的 `handle_key()` 函数中，在 `SPECIAL_KEYS` 字典添加新映射。

**协议：** 特殊键用字符串如 `'ctrl+alt+del'`，普通键直接传字符。

### 5.3 修改屏幕编码格式

**Agent 端：** `agent.py` 中 `capture_screen()` 函数负责截图 → `PIL.Image` → JPEG base64。
如需切换到 PNG 或 H.264，修改该函数返回值即可。

### 5.4 添加新的服务器消息类型

在 `server/index.js` 的 `wss.on('connection')` 回调中，在 `switch(msg.type)` 分支添加新的 case。

---

## 六、故障排查

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| 屏幕黑屏 | Agent 未启动 / 网络不通 | 检查 Agent 是否运行，`ping 8.137.116.121` |
| 拖拽失效 | `_held_button` 状态丢失 | 检查 `handle_mouse` 中 `move` 事件是否正确调用 `drag()` |
| 文件上传失败 | `static/` 目录无写权限 | 检查 `uploads/` 目录是否存在 |
| Agent 连接不上 | 密码错误或端口被封 | 确认 `ACCESS_PASSWORD` 和 `PORT` 环境变量 |
| 移动端触摸无反应 | Flutter `Listener` 未正确包裹屏幕区域 | 检查 `remote_page.dart` 中 `Listener` 的 parent widget |

---

## 七、重要约定

1. **不提交依赖包** — `node_modules/`、`__pycache__/`、`build/` 全部通过 `.gitignore` 排除
2. **服务器密码不放代码** — 通过环境变量 `ACCESS_PASSWORD` 注入
3. **Agent 主动连接** — 不需要 VPS 主动访问 Windows，Windows Agent 出站连接更安全
4. **拖拽必须保持按钮状态** — `move` 事件必须携带当前按住的按钮，`pyautogui.moveTo()` 会丢失按钮状态

---

## 八、联系方式

**Owner：** 魏超
**平台：** 飞书（ou_755999aa81d7950e4a2a5f0190f0326e）
