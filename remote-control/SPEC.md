# Remote Control System - 远程控制系统

> 当前版本：Phase 1 完成 ✅
> 最新更新：2026-04-03

---

## 一、当前架构

```
[手机浏览器] --WebSocket--> [VPS nginx :9080] --> [VPS Node Relay :21112]
                                                        ↕
                                              [Windows Agent (直接连接)]
                                                        ↑
                                              [Windows 桌面]
```

**访问地址：** http://8.137.116.121:9080
**密码:** `WeiChao_2026Ctrl!`

**关键改进（相比旧架构）：**
- Agent 直接连 VPS relay，**不需要 SSH 隧道**
- VPS relay 用 systemd 管理，开机自启
- 静态 HTML 由 node 服务器提供

**已知问题：**
- JPEG 编码帧率低（~5fps）
- 无 ID 寻址，每次需密码认证
- Agent 掉线后需手动重启

---

## 二、重构规划

### Phase 1：稳定化 ✅ 完成
- [x] 修复 HTML 重复函数定义（doUpload × 2）
- [x] Agent 固定 client_id（基于 MAC+主机名哈希）
- [x] Agent 自动重连（指数退避）
- [x] VPS relay systemd 服务化
- [x] 取消 SSH 隧道依赖（架构优化）
- [ ] SSH 隧道自动重连脚本（已写好，但不再需要）

### Phase 2：Rust 中继服务器
- [ ] 替换 Node.js，支持 500+ 并发
- [ ] Agent ID 注册 + WebRTC 信令
- [ ] 数据中继（打洞失败时）
- [ ] 部署到 VPS

### Phase 3：Python Agent 重构
- [ ] H.264 硬件编码（openh264）
- [ ] WebRTC DataChannel 传输
- [ ] 剪贴板同步
- [ ] Agent 开机自启动（Windows 服务）

### Phase 4：React 控制台
- [ ] 替换单 HTML 文件（移动端问题多）
- [ ] 组件化维护

### Phase 5：P2P 优化
- [ ] NAT 打洞（STUN/TURN）
- [ ] 连接质量自适应

---

## 三、技术选型

| 模块 | 当前 | 重构后 |
|------|------|--------|
| 中继服务器 | Node.js (21112) | Rust + tokio |
| 屏幕编码 | JPEG | H.264 (openh264) |
| 传输协议 | WebSocket | WebRTC DataChannel |
| Web 控制台 | 单 HTML | React + Vite |
| 服务管理 | nohup | systemd |
| NAT 穿透 | 无 | STUN + TURN 中继 |

---

## 四、部署信息

### 服务器 (VPS)
- 访问地址: `http://8.137.116.121:9080`
- Relay 端口: 21112
- nginx 反代: 9080 → 21112
- 服务管理: `systemctl status remote-control`
- 日志: `/var/log/remote-control.log`

### Agent (Windows)
- 路径: `D:\.openclaw\workspace\remote-control\agent\agent.py`
- 连接地址: `ws://8.137.116.121:9080/agent`
- 配置文件: `%APPDATA%\RemoteControlAgent\agent.json`
- 日志: `%APPDATA%\RemoteControlAgent\agent.log`
- 启动: `python agent.py`

### 文件同步
- 本地修改后需同步到 VPS: `scp index.html root@8.137.116.121:/home/weichao/remote-control-server/static/`
