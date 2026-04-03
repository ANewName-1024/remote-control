# Remote Control System - 远程控制系统

> 当前版本：Phase 1 完成 ✅，Phase 3 Delta Encoder 已实现
> 最新更新：2026-04-04

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

---

## 二、Phase 1 完成情况 ✅

- [x] 修复 HTML 重复函数定义（doUpload × 2）
- [x] Agent 固定 client_id（基于 MAC+主机名哈希）
- [x] Agent 自动重连（指数退避）
- [x] VPS relay systemd 服务化
- [x] 取消 SSH 隧道依赖（架构优化）
- [x] **submitPassword 密码验证后显示主机列表**（修复用户看不到在线主机的问题）
- [x] **浏览器端机器选择流程**（密码验证 → 显示列表 → 点击连接）

---

## 三、Phase 3 - Delta Screen Encoder（已实现）

### 核心模块
- `agent/enhanced_screen.py` - DeltaScreenCapture 类
  - 区块变化检测（64×64 像素区块）
  - 关键帧：每 3 秒强制一次（JPEG 质量 75）
  - Delta 帧：仅发送变化区域（JPEG 质量 65）
  - 相邻区域合并（减少传输量）
  - 二进制格式：big-endian (`>HHHH` x,y,w,h + `>I` size + JPEG)

### Delta Encoder 回归测试结果（5/5 PASS）
| 测试 | 结果 |
|------|------|
| T1 Keyframe 编码 | ✅ PASS (kf, 44KB) |
| T2 相同帧返回 None | ✅ PASS |
| T3 满帧变化检测 | ✅ PASS (510 blocks) |
| T4 小变化 32×32 检测 | ✅ PASS (4 blocks) |
| T5 二进制 big-endian 格式 | ✅ PASS |

### 发现并修复的 Bug
1. `_merge_blocks` 返回4值 `(x,y,w,h)` 但循环按2值 `(bx,by)` 解包 → 修复
2. `_block_changed` 里 prev row offset 计算错误 → 修复
3. quick hash 预检导致小变化漏检 → 去掉
4. 二进制格式大小端不统一 → 统一 big-endian

---

## 四、待解决

### 阻塞项
- ❌ **H.264 编码**：ffmpeg 安装失败（winget/choco 网络不通）

### 待验证（需真机测试）
- ⚠️ 端到端画面传输（手机浏览器连接后实际显示）
- ⚠️ 键盘输入传递
- ⚠️ 文件上传/下载

### 已知限制
- Agent 掉线后需手动重启（或等待自动重连）
- 分辨率较高时 JPEG 编码仍较大

---

## 五、技术指标

| 指标 | 数值 |
|------|------|
| 关键帧大小 | ~44KB (1920×1080) |
| Delta 帧大小 | ~5-20KB（取决于变化区域） |
| 区块大小 | 64×64 像素 |
| 关键帧间隔 | 3 秒 |
| Delta 检测算法 | 采样比较（8×8 网格） |
| 压缩 | 无（浏览器无 ZSTD 解压） |

---

## 六、部署信息

### Agent (Windows)
- 路径: `D:\.openclaw\workspace\remote-control\agent\agent.py`
- 连接地址: `ws://8.137.116.121:9080/agent`
- 启动: `python agent.py`

### VPS Relay
- 服务管理: `systemctl status remote-control`
- 日志: `/var/log/remote-control.log`
- 重启: `systemctl restart remote-control`

### 文件同步
- 本地修改后需同步到 VPS: `scp index.html root@8.137.116.121:/home/weichao/remote-control-server/static/`
