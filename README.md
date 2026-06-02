# Remote Control

> 自托管远程控制工具：浏览器 ⇄ VPS relay ⇄ Windows Agent

- **VPS relay (Node)**：Nginx 9080/8443 → Node 21112，转发 WebSocket
- **Windows Agent (Python)**：抓屏 / 输入 / 文件 / shell
- **Web Client**：浏览器，零安装
- **Mobile Client**：Flutter App（`projects/mobile/remote_control_app/`）

## 仓库结构

```
remote-control/
├── server/                # Node.js 中继 (VPS)
│   ├── index.js           # WS 路由 + 静态前端托管
│   └── package.json
├── agent/                 # Python 端 Agent (Windows)
│   ├── __init__.py
│   ├── __main__.py        # dispatcher (--mode=service|helper|auto)
│   ├── protocol.py        # 命名管道帧协议
│   ├── capture.py         # DXGI/mss/PIL 三级抓屏
│   ├── input_inject.py    # 鼠标键盘注入
│   ├── service.py         # Session 0 协调器
│   └── helper.py          # Session 1 worker
├── client/web/            # 浏览器客户端 (VPS 静态托管)
├── deploy/                # 部署脚本
│   ├── build-tar.ps1
│   ├── deploy-vps.ps1
│   ├── vps-install.sh
│   ├── install-windows-agent.ps1
│   └── remote-control.service
├── tests/                 # 自动化测试（详见 test_design.md）
├── AGENT.md               # ★ Windows Agent 架构说明
├── DEBUGGING.md           # 故障排查
├── SPEC.md                # 原始规格
└── test_design.md         # 测试设计（60+ 功能点 / 7 个套件）
```

## 快速开始

### VPS 端

```bash
# 部署（幂等）
pwsh deploy/build-tar.ps1
pwsh deploy/deploy-vps.ps1

# 检查状态
ssh -p 2222 root@8.137.116.121 'systemctl status remote-control'
curl http://8.137.116.121:9080/
```

### Windows 端

```powershell
# 安装 service（nssm 注册）
pwsh deploy/install-windows-agent.ps1

# 手动跑 helper 测抓屏
$env:RC_HELPER_TOKEN="<from service log>"
& python -m agent --mode=helper

# 手动跑 service
& python -m agent --mode=service
```

### 浏览器访问

打开 `http://8.137.116.121:9080/`，输入 `ACCESS_PASSWORD`，看到 Agent 桌面即可。

## 架构：为什么是双进程

| 进程 | Session | 职责 | 通信 |
|------|---------|------|------|
| **service** | 0 (SYSTEM) | WebSocket / 长连接 / 文件路由 | ⇄ VPS via WS<br>⇄ helper via 命名管道 |
| **helper** | 1+ (user) | 抓屏 / 注入 / 文件 I/O / shell | ⇄ service via 命名管道 |

**关键不变量**：
- 抓屏 / 鼠标 / 键盘 / 文件对话框 → **必须在 user session**（Session 0 看不见桌面）
- WS 长连接 / 服务注册 / 远程控制 / 心跳 → **SYSTEM 跑更稳**（机器重启后不用等用户登录）
- 进程间通信用 **命名管道**（同机最快，不走网络栈）

**锁屏抓屏限制**：DWM 在锁屏时拒绝所有 GDI/DXGI 访问，**双进程不能绕过**。
需要解锁屏抓屏得加 Windows.Graphics.Capture (UWP) 后端——见 `AGENT.md` §5 和 `capture.py` TODO。

## 详细文档

- **`AGENT.md`** — Agent 架构、IPC 协议、Session 切换、抓屏后端
- **`DEBUGGING.md`** — 故障排查（BitBlt 拒绝、WS 断连、helper 不启动 等）
- **`test_design.md`** — 测试设计 + 7 个套件清单
- **`SPEC.md`** — 原始产品需求

## 状态

| 组件 | 状态 |
|------|------|
| VPS relay (Node) | ✅ 已部署 systemd 稳定运行 |
| Web client | ✅ 浏览器可用 |
| Windows Agent v2.0 双进程 | ✅ 架构落地，IPC 烟测 HELLO+ACK 通过 |
| Windows Agent 帧传输 | ⏳ read_frame 在 PIPE_BYTE_STREAM 下待调试（独立 PR） |
| 锁屏抓屏 | ❌ DWM 阻断，2.1+ 加 WGC 后端 |
| install-windows-agent.ps1 双进程版 | ⏳ TODO |
| WebSocket ↔ helper 桥接 | ⏳ TODO |

## 协议 / 端口

- 21112 — Node relay（systemd）
- 9080 — Nginx → 21112 (HTTP)
- 8443 — 历史 HTTPS（未启用）
- `\\.\pipe\RemoteControlAgent_Cmd` — service ⇄ helper 控制
- `\\.\pipe\RemoteControlAgent_Frame` — helper → service 抓屏帧
