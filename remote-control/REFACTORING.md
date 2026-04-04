# Rust Relay 重构计划

> 目标：将 Node.js relay 重构为 Rust 版本，解决 nginx WebSocket 代理兼容性问题

## 一、背景

当前 Node.js relay 存在内存占用高、依赖复杂的问题，计划用 Rust 重写。

**当前状态：**
- Node.js relay：正常工作 ✅
- Rust relay (tokio-tungstenite)：已部署但 WebSocket 连接有问题 ❌
- 访问地址：http://8.137.116.121:9080
- 密码：WeiChao_2026Ctrl!

## 二、技术方案

### 2.1 当前问题

Node.js relay 的问题是内存占用高（~100MB+），Rust 版本预期 <10MB。

但 Rust relay (tokio-tungstenite) 遇到 nginx WebSocket 代理冲突：
- nginx 转发完整 HTTP upgrade 请求头
- `accept_async` 内部检测失败
- nginx 日志：`upstream prematurely closed connection while reading response header`

### 2.2 正确方案：Axum 框架

**核心思路：** 使用 `axum` 框架处理 HTTP 解析 + WebSocket 升级，Axum 内部处理 WS 握手，不与 nginx 冲突。

**依赖（待验证）：**
```toml
axum = "0.7"
tokio = { version = "1", features = ["rt-multi-thread", "net", "time", "sync", "macros"] }
tokio-tungstenite = "0.21"
futures-util = "0.3"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
uuid = { version = "1.0", features = ["v4"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["cors"] }
```

### 2.3 Axum WebSocket 处理示例

```rust
use axum::{
    extract::ws::{WebSocket, WebSocketUpgrade},
    response::Response,
    routing::get,
    Router,
};
use axum::extract::Path;

async fn ws_handler(ws: WebSocketUpgrade, Path(room): Path<String>) -> Response {
    ws.on_upgrade(|socket| handle_socket(socket, room))
}

async fn handle_socket(socket: WebSocket, room: String) {
    // WebSocket 处理逻辑
}
```

**关键点：**
- `WebSocketUpgrade` 自动处理 HTTP 解析和 WS 升级
- Axum 内部处理与 nginx proxy 兼容
- 不需要手动 peek() 或 from_raw_socket()

## 三、重构步骤

### Phase 1: 基础框架搭建
- [ ] 创建 `rust-relay-axum/` 目录
- [ ] 配置 Cargo.toml（axum + tokio + ws）
- [ ] 实现基础 HTTP API（/api/agents, /api/status）
- [ ] 在大内存环境编译测试

### Phase 2: WebSocket 路由
- [ ] 实现 /agent WS 端点
- [ ] 实现 /client WS 端点
- [ ] nginx WS proxy 测试

### Phase 3: 业务逻辑迁移
- [ ] Agent 注册和管理
- [ ] Client 管理和消息路由
- [ ] Heartbeat 超时处理
- [ ] 消息转发逻辑

### Phase 4: 部署
- [ ] 编译 release 版本
- [ ] 上传二进制到 VPS
- [ ] 配置 systemd 服务
- [ ] 灰度切换验证

## 四、大内存编译方案

### 方案 A：本地大内存机器编译
**目标机器：** 192.168.2.40（待确认 SSH 连通性）
- 需要安装 Rust 环境（rustc + cargo）
- 需要 Linux x86_64-unknown-linux-gnu target

### 方案 B：升级 VPS 到 16GB 内存
- 成本较高但最简单

### 方案 C：交叉编译（不推荐）
- 需要 Linux sysroot + OpenSSL
- 配置复杂，容易出错

## 五、预期效果

| 指标 | Node.js | Rust (Axum) |
|------|---------|--------------|
| 内存占用 | ~100MB | <10MB |
| CPU 占用 | 较高 | 极低 |
| 启动时间 | 秒级 | 毫秒级 |
| 二进制大小 | N/A | ~5MB |

## 六、风险与备选

### 风险
1. Axum 编译时间可能仍然较长
2. nginx WS proxy 配置可能需要调整
3. 已有 Node.js 逻辑迁移可能遗漏边界情况

### 备选方案
- 如果 Axum 仍然 OOM，考虑使用更轻量的 `mini-axum` 或纯 `tokio` + `tokio-tungstenite`（需要修复 WS 握手问题）
- 保持 Node.js relay 作为生产版本，Rust 版本作为优化尝试
