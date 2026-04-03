# Remote Control System - 远程控制系统

> 当前版本：Phase 1 稳定化进行中
> 最新更新：2026-04-03

---

## 一、当前架构

```
[手机浏览器] --HTTPS--> [VPS :9080] --SSH隧道--> [Node.js Relay :18799]
                                    |
                             [Python Agent :18789]
                                    |
                              [Windows 桌面]
```

**已知问题：**
- JPEG 编码帧率低（~5fps）
- 完全依赖 SSH 隧道，不稳定
- 无 ID 寻址，每次需密码认证
- 移动端偶发 JS 报错（已修）

---

## 二、重构规划

### Phase 1：稳定化 ✅ 进行中
- [x] 修复 HTML 重复函数定义导致 JS 报错
- [x] Agent 固定 client_id（基于 MAC+主机名哈希）
- [x] Agent 自动重连（指数退避）
- [x] 移动端点击聚焦问题（focus→click）
- [ ] SSH 隧道自动重连（autossh/watcher）

### Phase 2：Rust 中继服务器
- [ ] 替换 Node.js，支持 500+ 并发
- [ ] Agent ID 注册 + WebRTC 信令
- [ ] 数据中继（打洞失败时）
- [ ] 部署到 VPS

### Phase 3：Python Agent 重构
- [ ] H.264 硬件编码（openh264）
- [ ] WebRTC DataChannel 传输
- [ ] 固定配置文件
- [ ] 剪贴板同步

### Phase 4：React 控制台
- [ ] 替换单 HTML 文件
- [ ] 移动端可用
- [ ] 组件化维护

### Phase 5：P2P 优化
- [ ] NAT 打洞（STUN/TURN）
- [ ] 连接质量自适应

---

## 三、技术选型

| 模块 | 当前 | 重构后 |
|------|------|--------|
| 中继服务器 | Node.js (9080) | Rust + tokio |
| 屏幕编码 | JPEG | H.264 (openh264) |
| 传输协议 | WebSocket | WebRTC DataChannel |
| Web 控制台 | 单 HTML | React + Vite |
| NAT 穿透 | 无 | STUN + TURN 中继 |

---

## 四、部署信息

### 服务器
- VPS: `http://8.137.116.121:9080`
- 密码: `WeiChao_2026Ctrl!`
- 本地端口: 18799
- SSH 隧道: `ssh -p 2222 -i aliyun_key.pem -R 127.0.0.1:9080:127.0.0.1:18799`

### Agent
- 路径: `D:\.openclaw\workspace\remote-control\agent\agent.py`
- 配置文件: `%APPDATA%\RemoteControlAgent\agent.json`
- 日志: `%APPDATA%\RemoteControlAgent\agent.log`
- 重连脚本: `D:\.openclaw\workspace\remote-control\agent\reconnect-tunnel.bat`
