# AGENT.md - Windows 端 Agent

> 自托管的 Windows 远程控制 Agent（v2.x dual-process 架构）。
> 配套：**server** = Node 中继（部署在 VPS），**client** = 浏览器 / 移动 App。

## 1. 架构总览（v2.0+）

```
┌─────────── Windows 端机器 ──────────────────────────────┐
│                                                           │
│  Session 0 (SYSTEM)                                       │
│  ┌─────────────────────────────────────┐                  │
│  │ service.py  (--mode=service)        │                  │
│  │  • WebSocket ↔ VPS relay            │                  │
│  │  • WTSQueryUserToken → spawn helper │                  │
│  │  • 命名管道 CMD_PIPE 服务端         │◀─ auth token     │
│  │  • 命名管道 FRAME_PIPE 服务端       │   (env var)      │
│  │  • 路由：WS ⇄ helper                │                  │
│  └─────────┬───────────────────────────┘                  │
│            │  WTSQueryUserToken + CreateProcessAsUser     │
│            ▼                                              │
│  Session 1 (active user)                                  │
│  ┌─────────────────────────────────────┐                  │
│  │ helper.py  (--mode=helper)          │                  │
│  │  • DXGI / mss / PIL 三级抓屏        │                  │
│  │  • pyautogui + ctypes 输入注入      │                  │
│  │  • 文件下载 / 上传                  │                  │
│  │  • shell exec                       │                  │
│  └─────────────────────────────────────┘                  │
└───────────────────────────────────────────────────────────┘
```

**为什么需要双进程？**
- 抓屏 / 注入 / 文件对话框都要求**用户交互 session (Session 1+)**
- Windows 服务跑在 Session 0（SYSTEM），不能直接做这些事
- helper 跑在用户 session，service 负责长连接（WS）和协调

## 2. 模块清单

| 文件 | 行数 | 角色 | 关键 API |
|------|------|------|----------|
| `__init__.py` | 18 | 包标记 | `__version__` |
| `__main__.py` | 56 | dispatcher | `python -m agent --mode=service\|helper\|auto` |
| `protocol.py` | 142 | 管道帧协议 | `pack`, `read_envelope`, `send_msg`, `send_frame` |
| `capture.py` | 130 | 抓屏后端选择 | `ScreenCapture(backend='auto')` |
| `input_inject.py` | 158 | 输入注入 | `mouse_move`, `mouse_click`, `key_tap`, `type_text` |
| `service.py` | 410 | Session 0 协调 | `PipeServer.start(on_hello)`, `spawn_helper_in_user_session` |
| `helper.py` | 320 | Session 1 worker | `run_helper()` + `frame_sender` 线程 |

## 3. IPC 协议（service ⇄ helper）

**两条命名管道**（避免阻塞和消息混淆）：

| 管道 | 方向 | 帧格式 | 用途 |
|------|------|--------|------|
| `\\.\pipe\RemoteControlAgent_Cmd` | 双向 | `[4-byte BE len][UTF-8 JSON]` | 控制消息（HELLO, INPUT, EXEC, FILE_*） |
| `\\.\pipe\RemoteControlAgent_Frame` | helper→service | `[4-byte BE len][struct('>IQ', seq, ts_ms)][RGB raw]` | 抓屏帧（高吞吐） |

**PIPE_BYTE_STREAM 模式** + **长度前缀 framing**（不要用 PIPE_TYPE_MESSAGE——`ReadFile(h, N)` 会返回整条 message 而忽略 N）

**控制消息类型**（见 `protocol.py`）：
- `MSG_HELLO` / `MSG_HELLO_ACK` — 握手 + 鉴权
- `MSG_HEARTBEAT` — 心跳
- `MSG_INPUT_MOUSE` / `MSG_INPUT_KEY` / `MSG_INPUT_HOTKEY` / `MSG_INPUT_TYPE` / `MSG_INPUT_CLIPBOARD_SET` — 输入
- `MSG_INPUT_EXEC` / `MSG_INPUT_FILE_DOWNLOAD` / `MSG_INPUT_FILE_UPLOAD` — 文件 / shell
- `MSG_CAPTURE_BATCH` — 帧批量
- `MSG_EXEC_RESULT` / `MSG_FILE_DOWNLOAD_READY` / `MSG_FILE_DOWNLOAD_CHUNK` / `MSG_FILE_UPLOAD_ACK` — 反向
- `MSG_STATUS` — helper 状态
- `MSG_BYE` — 优雅断开

**鉴权**：service 启动时 `secrets.token_urlsafe(32)` 生成 32 字符 token，通过 `RC_HELPER_TOKEN` 环境变量传给 helper。helper 在 HELLO 消息里带 token，service 不匹配就断开。

## 4. 进程身份切换（Session 0 → Session 1）

```python
# service.py: spawn_helper_in_user_session()
1. WTSQueryUserToken(WTS_CURRENT_SERVER_HANDLE, session_id)
   → 拿 user token
2. DuplicateTokenEx(token, TOKEN_ALL_ACCESS, ..., SecurityImpersonation, TokenPrimary)
   → 转成可用的 primary token
3. CreateProcessAsUserW(
     token, None, python_cmd, ...,
     lpDesktop='Default',        # 必须：否则 helper 没有 desktop
     dwCreationFlags=CREATE_UNICODE_ENVIRONMENT | CREATE_NEW_CONSOLE,
     lpEnvironment=block,        # 注入 RC_HELPER_TOKEN
     ...
   )
```

**坑**：
- `OpenProcessToken` 拿到 SYSTEM token，`CreateProcessAsUser` 会因"主令牌不可用于交互"失败 → 必须 `WTSQueryUserToken`
- `lpDesktop='Default'` 不可省，否则 helper 在 hidden station 跑（无法访问 user desktop）
- `STARTF_USESHOWWINDOW | SW_HIDE` 让 helper 不弹黑窗

## 5. 抓屏后端选择

| 后端 | 库 | 速度 | 锁屏下 | 推荐场景 |
|------|------|------|--------|----------|
| DXGI Desktop Duplication | `dxcam` | ⚡⚡⚡ | ❌（DWM 阻断） | 解锁状态，最快 |
| GDI BitBlt (mss) | `mss` | ⚡⚡ | ❌（DWM 阻断） | 解锁状态，DXGI 不可用时 |
| PIL.ImageGrab | `Pillow` | ⚡ | ❌（DWM 阻断） | 最后 fallback |

**auto 模式**：`dxcam` → `mss` → `PIL.ImageGrab`，运行时探测可用性。

**锁屏限制**：DWM 在锁屏时是唯一能访问 GDI/DXGI 的进程。所有这些后端都会 `E_ACCESSDENIED`。
**双进程架构本身不能解决这个问题**——helper 跑在 user session 也被 DWM 拒。

**真解锁屏抓屏**（v2.1+ TODO）：
- 加 `Windows.Graphics.Capture (UWP)` 后端
- 需在 helper 里调 `GraphicsCapturePicker`，初始化 COM STA
- 详见 `capture.py` 的 TODO 注释

## 6. 输入注入

| 路径 | 库 | 适用 |
|------|------|------|
| 优先 | `pyautogui` | 跨平台接口干净 |
| fallback | `ctypes + SendInput` | pyautogui 在 RDP/某些终端无响应时 |

**坑**：
- `pyautogui` 在 Windows 默认有 `pyautogui.FAILSAFE`：鼠标移到 (0,0) 抛 `FailSafeException`。helper 启动时 `pyautogui.FAILSAFE = False`。
- `SendInput` 必须用 `ctypes` 而非 `win32api.keybd_event`（后者在新版 Windows 上已 deprecated）
- 绝对坐标需要 `MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK` flags

## 7. 启动模式

```bash
# Service（SYSTEM / Session 0）
python -m agent --mode=service --config /path/to/.env

# Helper（用户 Session 1，由 service 自动拉起）
python -m agent --mode=helper
# ↑ 通过 RC_HELPER_TOKEN 环境变量认证

# Auto（旧版兼容，单进程模式）
python -m agent --mode=auto
# ↑ 等价于跑 agent.agent.WebSocketClient
```

**部署**：用 `deploy/install-windows-agent.ps1` 注册 service（nssm 或 schtasks）。

## 8. 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `RC_CONFIG_DIR` | 是 | 配置目录（`%APPDATA%\RemoteControlAgent\`） |
| `RC_HELPER_TOKEN` | service 模式 | helper 鉴权 token（service 启动时生成） |
| `ACCESS_PASSWORD` | 是 | WebSocket 认证密码（与 server 一致） |
| `SCREEN_FPS` | 否 | 抓屏帧率（默认 10） |
| `WS_URL` | service 模式 | VPS relay URL（如 `ws://8.137.116.121:21112`） |
| `PYTHONIOENCODING` | 是 | 强制 `utf-8`（Windows 默认 cp936） |

完整模板：`deploy/.env.windows`

## 9. 调试清单

| 症状 | 检查 |
|------|------|
| helper 启动后立即退出 | 看 `RC_HELPER_TOKEN` 是否一致 |
| service 报 "token mismatch" | helper 的 token env 没传过去；查 `CreateProcessAsUser` 的 lpEnvironment |
| 抓屏 `拒绝访问` | 机器在锁屏状态（`OpenInputDesktop=0` / `LogonUI` 进程） |
| 输入无响应 | helper 跑的 session 不是用户那个（`wts_session_id` 0 = SYSTEM） |
| 管道 `all instances are busy` | service 的 `cmd_conn` / `frame_conn` 泄漏；重启 service |

日志：`%APPDATA%\RemoteControlAgent\logs\agent.log`（轮转 5 × 5MB）

## 10. 版本迁移

| 版本 | 模式 | 状态 |
|------|------|------|
| 1.x | 单进程 WebSocketClient | 已废弃（`--mode=auto` 兼容） |
| 2.0+ | 双进程 service+helper | **当前** |
| 2.1+ (TODO) | + WGC UWP 后端 | 解锁锁屏抓屏 |

---

详见 `DEBUGGING.md`（抓屏 / 输入 / 锁屏具体场景）。
