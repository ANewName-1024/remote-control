# Rust Relay 问题排查记录

> 详细记录 Rust relay 开发过程中遇到的问题及解决方案

---

## 问题 1：VPS 编译 OOM（已尝试 - 失败）

**环境：** VPS 8.137.116.121（8GB 内存）

**问题描述：**
尝试使用 `cargo build --release` 编译 axum 版本，编译过程中 OOM（Out of Memory）被杀。

**尝试的错误方案：**
```bash
# 1. 使用 swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 2. 限制编译 jobs
cargo build --release -j 2

# 3. 使用 tokio/unix-socket only features
# （仍 OOM，因为 hyper + tls 依赖太大）
```

**根因：** axum 依赖 hyper、tower、tower-http 等，编译时 LLVM 内存占用峰值超过 8GB。

**状态：** ❌ 放弃，需大内存环境

---

## 问题 2：tokio-tungstenite + nginx WS proxy 冲突

**环境：** VPS 8.137.116.121 + nginx reverse proxy

**问题描述：**
使用 `tokio-tungstenite` 的 `accept_async()` 接受 WebSocket 连接时，nginx 返回 502：
```
upstream prematurely closed connection while reading response header
```

**代码：**
```rust
async fn handle_agent(state: AppState, stream: TcpStream) {
    let ws = match accept_async(stream).await {
        Ok(ws) => ws,
        Err(e) => { tracing::warn!("WS accept error: {}", e); return; }
    };
    // ...
}
```

**nginx 配置：**
```nginx
location /agent {
    proxy_pass http://127.0.0.1:21112/agent;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400;
}
```

**尝试的修复方案：**

### 方案 2.1：peek + accept_async（❌ 失败）

```rust
let mut buf = [0u8; 2048];
let n = match stream.peek(&mut buf).await {
    Ok(n) if n > 0 => n,
    _ => return,
};
// peek 消费了 TCP buffer，导致 accept_async 失败
let ws = match accept_async(stream).await { ... };
```

**结果：** peek 消费了数据，accept_async 读取不到 HTTP upgrade 请求，失败。

### 方案 2.2：手动 WebSocket 握手（❌ 部分成功）

使用 `tokio_tungstenite::WebSocketStream::from_raw_socket` 手动完成握手：

```rust
let mut buf = [0u8; 2048];
let n = stream.read(&mut buf).await?;
let request = std::str::from_utf8(&buf[..n])?;

let is_ws = request.contains("Upgrade: websocket");
let key = request.lines()
    .find(|l| l.to_lowercase().starts_with("sec-websocket-key:"))
    .map(|l| l.split(':').nth(1).unwrap_or("").trim())
    .unwrap_or("");

// 发送握手响应
let response = format!(
    "HTTP/1.1 101 Switching Protocols\r\n\
     Upgrade: websocket\r\n\
     Connection: Upgrade\r\n\
     Sec-WebSocket-Accept: {}\r\n\
     \r\n",
    compute_accept_key(key)
);
stream.write_all(response.as_bytes()).await?;
stream.flush().await?;

// 使用 from_raw_socket
let ws = WebSocketStream::from_raw_socket(
    stream,
    Role::Server,
    Some(websocat_protocol::Url::parse("http://localhost")?),
).await;
```

**结果：** 编译成功，连接仍有问题（nginx 转发后 WS 握手不完整）。

### 方案 2.3：Axum 框架（✅ 正确方案，未验证）

Axum 的 `WebSocketUpgrade` 自动处理 HTTP 解析和 WS 升级，不与 nginx 冲突。

**问题：** 需要大内存编译。

**状态：** ⏳ 待验证

---

## 问题 3：Windows 交叉编译（❌ 放弃）

**目标：** 在 Windows (192.168.2.32) 上交叉编译 Linux 二进制

**问题：** 需要 Linux sysroot + OpenSSL 库，配置复杂。

**错误信息示例：**
```
could not find native static library `ssl`, `crypto`, or `zlib`
```

**状态：** ❌ 放弃

---

## 问题 4：192.168.2.40 SSH 连接失败

**环境：** 目标机器 192.168.2.40（Linux）

**问题描述：**
- ping 通
- SSH 端口 22 超时
- 可能原因：防火墙 / SSH 服务未运行 / 非标准端口

**排查步骤：**
```bash
# 1. 检查端口连通性
Test-NetConnection -ComputerName 192.168.2.40 -Port 22

# 2. 扫描常见端口
# 22, 2222, 8022, 2200, 22222
```

**状态：** ❌ 待排查

---

## 问题 5：192.168.2.32 是 Windows（非 Linux）

**环境：** 192.168.2.32

**发现：** `uname` 命令不存在，确认为 Windows 11 系统。

**问题：** 无法直接在该机器上编译 Linux 静态二进制。

**状态：** ❌ 不适合 Rust Linux 编译

---

## 总结：待办事项

| 问题 | 状态 | 解决方案 |
|------|------|----------|
| VPS OOM | ❌ | 寻找大内存机器（192.168.2.40） |
| WS 握手冲突 | ⏳ | Axum 方案，待编译验证 |
| 192.168.2.40 SSH | ❌ | 确认 SSH 服务状态和端口 |
| 192.168.2.32 Windows | ✅ 已知 | 不适用 |
| Node.js relay | ✅ 正常 | 作为生产版本备用 |
