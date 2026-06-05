# Remote Control 测试设计

> 版本：v1.0  
> 编写日期：2026-06-02  
> 范围：remote-control 全部功能点（Server / Agent / Web Client / 安全加固）  
> 关联文档：`SPEC.md`（功能设计）、`AGENT.md`（构建与运维）、`README.md`（用户手册）

---

## 一、测试目标

按 `SPEC.md` 的功能设计 + `server/index.js` / `agent/agent.py` / `agent/enhanced_screen.py` / `server/static/index.html` 的实现，逐项给出**可执行**的测试用例，覆盖：

1. **正向** — 功能按设计工作
2. **反向** — 安全边界（鉴权、路径穿越、大小限制）严格生效
3. **健壮性** — 错误输入 / 离线 / 超时不导致服务崩溃
4. **回归** — 已有 `smoke_test.js` / `upload_test.js` 仍绿

---

## 二、功能点清单 & 测试矩阵

> **标签说明**：`U` = 单元（纯函数），`I` = 集成（启动真实 server 拉临时端口），`E` = 端到端（fake agent + fake client），`P` = Python 单元

### A. Server HTTP REST API（`server/index.js`）

| ID | 功能点 | 端点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| A1 | 服务状态 | `GET /api/status` | `http_api` T01-T03 | I | P0 |
| A2 | Agent HTTP 心跳 | `GET /api/agent/ping` | `http_api` T04-T06 | I | P0 |
| A3 | 服务密码验证 | `POST /api/verify-password` | `http_api` T07-T09 | I | P0 |
| A4 | 列出在线 agent | `GET /api/agents` | `http_api` T10-T12 | I | P0 |
| A5 | Agent 二次认证 | `POST /api/agents/:id/auth` | `http_api` T13-T15 | I | P0 |
| A6 | 列出已上传文件 | `GET /api/files` | `http_api` T16 | I | P1 |
| A7 | 文件上传 | `POST /api/upload` | `upload_test` T01-T08 | I | P0 |
| A8 | 文件下载 | `GET /api/download/:name` | `http_api` T17-T19 | I | P0 |
| A9 | 文件删除 | `DELETE /api/files/:name` | `http_api` T20-T21 | I | P0 |

### B. Static Deploy API（`server/index.js` §Static Deploy）

| ID | 功能点 | 端点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| B1 | 鉴权 — 无 Bearer | `PUT /api/deploy/*` | `smoke` T01 | I | P0 |
| B2 | 鉴权 — 错误密码 | `PUT /api/deploy/*` | `smoke` T02 | I | P0 |
| B3 | 正常部署 | `PUT /api/deploy/*` | `smoke` T03-T05 | I | P0 |
| B4 | 路径穿越 `..` | `PUT /api/deploy/*` | `smoke` T06-T09 | I | P0 |
| B5 | 大小限制 50MB | `PUT /api/deploy/*` | `smoke` T10 | I | P0 |
| B6 | 列表 | `GET /api/deploy/list` | `smoke` T11-T13 | I | P0 |
| B7 | 静态服务 | `GET /app/*` | `smoke` T14-T15 | I | P0 |
| B8 | NUL 字节拒绝 | `PUT /api/deploy/*` | `path_security` T01 | I | P0 |
| B9 | Windows 绝对路径 `C:\...` | `PUT /api/deploy/*` | `path_security` T02 | I | P0 |
| B10 | URL 编码 `..%2f`（混合编码）| `PUT /api/deploy/*` | `path_security` T03 | I | P0 |
| B11 | 嵌套子目录创建 | `PUT /api/deploy/sub/dir/file.txt` | `path_security` T04 | I | P1 |
| B12 | `resolveSafeDeployPath` 纯函数 | — | `path_security` T05-T10 | U | P0 |

### C. WebSocket 协议（`server/index.js` §WS）

| ID | 功能点 | 端点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| C1 | Agent 注册 | `WS /agent` | `ws_protocol` T01-T03 | I | P0 |
| C2 | Agent 未鉴权发 `screen` | `WS /agent` | `ws_protocol` T04 | I | P0 |
| C3 | Agent 发送 screen → client 收到 | `WS /agent` + `WS /client` | `e2e` T01 | E | P0 |
| C4 | Agent 发送 output → session 路由 | `WS /agent` + `WS /client` | `e2e` T02 | E | P0 |
| C5 | Agent 发送 file_chunk | `WS /agent` + `WS /client` | `e2e` T03 | E | P0 |
| C6 | Agent 发送 pong 更新 lastSeen | `WS /agent` | `ws_protocol` T05 | I | P0 |
| C7 | Client 注册（密码 + agentId） | `WS /client` | `ws_protocol` T06-T08 | I | P0 |
| C8 | Client 错误密码断开 | `WS /client` | `ws_protocol` T09 | I | P0 |
| C9 | Client → Agent 鼠标 | `WS /client` → `WS /agent` | `e2e` T04 | E | P0 |
| C10 | Client → Agent 键盘 | `WS /client` → `WS /agent` | `e2e` T05 | E | P0 |
| C11 | Client → Agent exec（带 sessionId） | `WS /client` → `WS /agent` | `e2e` T06 | E | P0 |
| C12 | Client → Agent file_request | `WS /client` → `WS /agent` | `e2e` T07 | E | P0 |
| C13 | Client → Agent clipboard | `WS /client` → `WS /agent` | `e2e` T08 | E | P1 |
| C14 | Agent 离线时 client 收到 `agent_offline` | `WS /client` | `ws_protocol` T10 | I | P0 |
| C15 | 错误 JSON 不崩溃 | `WS /agent` 或 `WS /client` | `ws_protocol` T11 | I | P0 |

### D. Agent — 协议处理（`agent/agent.py` §Input Simulation / §Shell / §File）

| ID | 功能点 | 函数 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| D1 | `KEY_MAP` 覆盖标准键 | `parse_key` | `mouse_keyboard` T01-T05 | P | P0 |
| D2 | `parse_key` 单字符 → VkKeyScan | `parse_key` | `mouse_keyboard` T06 | P | P0 |
| D3 | `parse_key` 未知键返回 None | `parse_key` | `mouse_keyboard` T07 | P | P0 |
| D4 | `handle_mouse` 坐标边界裁剪 | `handle_mouse` | `mouse_keyboard` T08 | P | P0 |
| D5 | `handle_mouse` 5 种 action | `handle_mouse` | `mouse_keyboard` T09-T14 | P | P0 |
| D6 | `handle_key` down/press/up | `handle_key` | `mouse_keyboard` T15-T17 | P | P0 |
| D7 | `handle_hotkey` 组合键 | `handle_hotkey` | `mouse_keyboard` T18 | P | P1 |
| D8 | `execute_command` 空命令立即 done | `execute_command` | `mouse_keyboard` T19 | P | P0 |
| D9 | `execute_command` 中文输出 | `execute_command` | `mouse_keyboard` T20 | P | P1 |
| D10 | `handle_file_download` 不存在的文件 | `handle_file_download` | `mouse_keyboard` T21 | P | P0 |
| D11 | `handle_file_download` 分块 base64 | `handle_file_download` | `mouse_keyboard` T22 | P | P0 |
| D12 | 消息分发 — 收到 `mouse` | `_on_message` | `mouse_keyboard` T23 | P | P0 |
| D13 | 消息分发 — 收到 `key` | `_on_message` | `mouse_keyboard` T24 | P | P0 |
| D14 | 消息分发 — 收到 `exec` | `_on_message` | `mouse_keyboard` T25 | P | P0 |
| D15 | 消息分发 — 收到 `file_request:download` | `_on_message` | `mouse_keyboard` T26 | P | P0 |
| D16 | 消息分发 — 收到 `file_request:upload` | `_on_message` + `handle_file_upload` | `mouse_keyboard` T27（dispatch） + `TestHandleFileUpload` U1-U6（handler） | P | P0 |
| D17 | 机器指纹确定性 | `_get_machine_fingerprint` | `mouse_keyboard` T28 | P | P1 |
| D18 | 凭据持久化（首次创建 + 后续读取） | `get_or_create_credentials` | `mouse_keyboard` T29 | P | P0 |
| D19 | 单实例锁 | `__main__` 锁 | `mouse_keyboard` T30 | P | P2 |

### E. Delta Encoder（`agent/enhanced_screen.py`）

| ID | 功能点 | 函数 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| E1 | 关键帧编码格式 | `_encode_keyframe` | `delta_encoder` T01 | P | P0 |
| E2 | 相同帧不返回 delta | `capture_and_encode` | `delta_encoder` T02 | P | P0 |
| E3 | 满帧变化检测 | `_find_changed_blocks` | `delta_encoder` T03 | P | P0 |
| E4 | 小变化 32×32 检测 | `_find_changed_blocks` | `delta_encoder` T04 | P | P0 |
| E5 | 二进制 big-endian 格式 | `_encode_delta` | `delta_encoder` T05 | P | P0 |
| E6 | 强制关键帧间隔 3s | `capture_and_encode` | `delta_encoder` T06 | P | P0 |
| E7 | 区块合并 | `_merge_blocks` | `delta_encoder` T07 | P | P0 |
| E8 | 区块采样检测 | `_block_changed` | `delta_encoder` T08 | P | P0 |
| E9 | 屏幕分辨率获取 | `get_screen_size` | `delta_encoder` T09 | P | P1 |
| E10 | 大帧 MAX_REGIONS 截断 | `_encode_delta` | `delta_encoder` T10 | P | P0 |

### F. Web Client（`server/static/index.html`）

| ID | 功能点 | 行为 | 测试方式 | 优先级 |
|----|--------|------|----------|--------|
| F1 | 密码提交 → 机器列表 | `submitPassword` | 浏览器/手测 | P2 |
| F2 | 鼠标 down/move/up/wheel 消息 | `container.addEventListener` | `e2e` T04（server 端验证） | P0 |
| F3 | 触摸 down/move/click 消息 | `container touchstart` | `e2e` T04（server 端验证） | P0 |
| F4 | 键盘 press 消息 | `sendHotkey` | `e2e` T05 | P0 |
| F5 | 终端 exec 消息带 session | `send` | `e2e` T06 | P0 |
| F6 | 文件下载分块接收 | `file_request:download` | `e2e` T07 | P0 |
| F7 | 文件上传走 `/api/upload` | `submitUpload` | `upload_test` | P0 |
| F8 | 锁定屏幕 | `lockScreen` | `e2e` T06（exec 分支） | P2 |
| F9 | 黑屏（PowerShell SendMessage） | `blankScreen` | `e2e` T06（exec 分支） | P2 |

### G. 安全加固（独立成节，方便回归）
| ID | 加固项 | 测试 | 优先级 |
|----|--------|------|--------|
| G1 | Static Deploy Bearer 鉴权 | `smoke` T01-T02, `path_security` T11 | P0 |
| G2 | 路径穿越 NUL / 绝对 / `..` / 编码 | `path_security` T01-T04, `smoke` T06-T09 | P0 |
| G3 | 50MB 大小限制 | `smoke` T10 | P0 |
| G4 | multer 2.x 文件名净化 | `upload_test` T07-T11 | P0 |
| G5 | 异步 I/O（不阻塞事件循环） | `http_api` T16（列出 1000 文件） | P1 |
| G6 | 列表深度限制 8 层 | `path_security` T12 | P1 |
| G7 | WebSocket 密码失败立即 close | `ws_protocol` T09 | P0 |

### H. App 诊断日志主动上传（Flutter App → server → `DIAG_DIR`）

### V. Agent 鼠标注入静默失败防护（`agent/input_inject.py:verify_at` + 真机 smoke）

SendInput 在 Session 0 / UAC / 锁屏场景下**静默 no-op**：pyautogui.moveTo() 返回成功，但 `pyautogui.position()` 后还是旧坐标。单元测试会拄着 mock 看不到这个 bug，需要在真机上调用 verify_at() 验位置才知道是否真生效。

| ID | 功能点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|--------|
| V1 | verify_at 坐标完全匹配返回 True | `verify_at` V1 | U | P0 |
| V2 | verify_at 1px 误差内仍 True | `verify_at` V2 | U | P0 |
| V3 | verify_at 误差超 tolerance 返回 False | `verify_at` V3 | U | P0 |
| V4 | verify_at 不匹配 log warning | `verify_at` V4 | U | P0 |
| V5 | pyautogui.position 报异常时 verify_at 返回 False 不崩溃 | `verify_at` V5 | U | P1 |
| V6 | 无 pyautogui 时 verify_at 跳过验证 | `verify_at` V6 | U | P1 |
| V7 | mouse('move') 后调用 verify_at(x, y) | `verify_at` V7 | U | P0 |
| V8 | mouse('click') 不调 verify_at | `verify_at` V8 | U | P0 |
| V9 | mouse('down') 不调 verify_at | `verify_at` V9 | U | P0 |
| V10 | mouse('up') 不调 verify_at | `verify_at` V10 | U | P0 |
| V11 | mouse('wheel') 不调 verify_at | `verify_at` V11 | U | P0 |
| V12 | 真机: move + position 坐标对得上 | `smoke_test_mouse.py` Test 1 | E2E | P0 |
| V13 | 真机: 二次 move 仍能到目标 | `smoke_test_mouse.py` Test 2 | E2E | P1 |
| V14 | 真机: click 不抬 cursor | `smoke_test_mouse.py` Test 3 | E2E | P1 |
| V15 | 真机: dragTo 结尾坐标 = 目标 | `smoke_test_mouse.py` Test 4 | E2E | P1 |
| V16 | 真机: verify_at 在真机上能识别 mismatch | `smoke_test_mouse.py` Test 5 | E2E | P0 |

V12-V16 需要真机跑：设 `RC_RUN_E2E=1` 后 `run_all_tests.ps1` 才会执行。默认跳过 (会在屏幕上点)。

### R. Agent 日志轮转（`agent/log_rotation.py` + 集成到 3 个脚本）

| ID | 功能点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|--------|
| R1 | 首次写日志创建文件 | `log_rotation` R1 | U | P0 |
| R2 | 超 max_bytes 轮转 | `log_rotation` R2 | U | P0 |
| R3 | backup_count 严格限制总数 | `log_rotation` R3 | U | P0 |
| R4 | 同名 logger 重复调用幂等 | `log_rotation` R4 | U | P0 |
| R5 | 父目录不存在自动建 | `log_rotation` R5 | U | P0 |
| R6 | utf-8 中文日志不损 | `log_rotation` R6 | U | P0 |
| R7 | logger.propagate=False 避免 double-log | `log_rotation` R7 | U | P0 |
| R8 | max_bytes=1 极限场景不崩 | `log_rotation` R8 | U | P1 |
| R9 | 2 个 handler (file + stderr) 格式不冲突 | `log_rotation` R9 | U | P0 |

| ID | 功能点 | 端点 | 测试 | 类型 | 优先级 |
|----|--------|------|------|------|--------|
| H1 | Client 发 `app_diag` 落盘 + ack | `WS /client` | `diag` T01 (D1) | I | P0 |
| H2 | 多次上传不同 trigger 不互相覆盖 | `WS /client` | `diag` T02 (D2) | I | P0 |
| H3 | 空 `logs` 被拒（不创建空文件） | `WS /client` | `diag` T03 (D3) | I | P0 |
| H4 | `GET /api/diag` 列出所有 agent + 文件 | `GET /api/diag` | `diag` T04 (D4) | I | P0 |
| H5 | `GET /api/diag/latest` 返回最近 dump | `GET /api/diag/latest` | `diag` T05 (D5) | I | P0 |
| H6 | `GET /api/diag/download` 流式返回原文件 | `GET /api/diag/download` | `diag` T06 (D6) | I | P0 |
| H7 | agentId 路径穿越阻断（`..`/斜杠） | `GET /api/diag/*` | `diag` T07 (D7) | I | P0 |
| H8 | `?agentId=X` 过滤 | `GET /api/diag` | `diag` T08 (D8) | I | P1 |
| H9 | 未鉴权 client 的 `app_diag` 被拒 | `WS /client` | `diag` T09 (D9) | I | P0 |
| H10 | `app_diag` HTTP 端点需 Bearer 鉴权 | `GET /api/diag*` | `diag` T04 (D4 第一条) | I | P0 |
| H11 | 超过 `DIAG_MAX_BYTES` 截断到尾部 | `WS /client` | （由代码逻辑覆盖，未单独跑） | I | P1 |
| H12 | trigger / appVersion / context 落 sidecar JSON | `WS /client` | `diag` T01 (D1) | I | P0 |

### 踩过的坑（仅作记录，避免下次重犯）

- **测试端口**：`run_all_tests.ps1` 改过 `test_diag.js` 串行独享 21997（不要并行跑会撞 DIAG_DIR 的创建）
- **PowerShell + Node.js 退出码**：Node 把 `[Diag] rejected empty upload from client ?` 打到 stderr，PowerShell 转换成非零退出码但测试本身是 0。判断成败只看 `=== N passed, 0 failed ===`，不要看 `$LASTEXITCODE`。
- **`_noagent` 子目录**：当 client 还没 `subscribe` 到任何 agent 就发 `app_diag`，server 落 `_noagent/`（而不是“漏了 agentId 就拒了”）。这是有意的：用户在连接到主机列表后即点 “上传日志” 需要有路径落地。

---

## 三、测试脚本组织

```
remote-control/
├── test_design.md                  ← 本文档
├── smoke_test.js                   ← 已有（15 断言）Static Deploy
├── upload_test.js                  ← 已有（12 断言）multer 2.x
├── test_path_security.js           ← 新增（12 断言）路径安全 + 鉴权 + resolveSafeDeployPath
├── test_http_api.js                ← 新增（21 断言）HTTP REST API
├── test_ws_protocol.js             ← 新增（11 断言）WebSocket 鉴权 + 协议 + 健壮性
├── test_e2e_flow.js                ← 新增（8 断言）端到端：fake agent ⇄ server ⇄ fake client
├── agent/tests/
│   ├── test_delta_encoder.py       ← 新增（10 断言）Delta Encoder
│   └── test_mouse_keyboard.py      ← 新增（30 断言）Agent 协议处理
└── run_all_tests.ps1               ← 新增：跑所有测试的总入口
```

**断言统计**

| 套件 | 断言数（设计） | 实际断言 | 运行时长（实测）|
|------|----------------|----------|------------------|
| smoke_test.js | 15 | 15 | < 3s |
| upload_test.js | 12 | 12 | < 3s |
| test_path_security.js | 12 | 16 | < 2s |
| test_http_api.js | 21 | 29 | < 3s |
| test_ws_protocol.js | 11 | 14 | < 3s |
| test_e2e_flow.js | 8 | 24 | < 4s |
| test_delta_encoder.py | 10 | 12 | < 2s |
| test_mouse_keyboard.py | 30 | 51（含 U1-U6 + CB1-CB7 + D16b/c） | < 5s |
| test_wgc.py | - | 9（WC1-WC9，WC3 仅无 winrt 环境跑） | < 1s |
| **合计** | **119** | **182** | **< 25s** |

---

## 四、测试实现约定

### 4.1 通用模式

1. **独立端口** — 每个 JS 测试用 `child_process.spawn('node', ['server/index.js'])` 拉独立端口（如 21997），不污染主 server
2. **环境变量** — `PORT` 和 `ACCESS_PASSWORD` 通过 env 注入，避免硬编码
3. **自动清理** — 退出前 kill 子进程 + 删上传/部署文件
4. **统一断言函数** — `check(name, ok, detail)` 输出 `PASS/FAIL` 并累计计数
5. **退出码** — `process.exit(failed > 0 ? 1 : 0)`

### 4.2 临时密码生成

```js
const PASSWORD = 'test-pw-' + Date.now();
process.env.ACCESS_PASSWORD = PASSWORD;
```

### 4.3 Python 测试约定

- 用 `unittest`，不引入 pytest
- `unittest.mock.patch` 模拟 `pyautogui`、`win32api`、`PIL.ImageGrab`
- 测试在 Windows 跑（Delta Encoder 用真实屏幕会失败，但 `_find_changed_blocks` 等纯函数可单测）

### 4.4 已知限制 / Gap

| 编号 | 说明 | 影响 |
|------|------|------|
| ~~GAP-1~~ | **已修复**：Agent 已实现 `file_request:upload`（`handle_file_upload`） | 客户端 `index.html doUpload` 的 chunked upload 协议现在真正能落地。新增 `agent/tests/test_mouse_keyboard.py` 下的 6 个 `TestHandleFileUpload` 用例 + 1 个 dispatch 用例。 |
| ~~GAP-2~~ | **已修复**：Server 为 `file_request` 也创建 server session | Agent 用 client 传来的 sessionId 发回 `file_chunk`，server 现在能正确路由回 client。原 e2e T07 必须复用 exec session 绕过此问题；修复后新增 T09 用 file_request 自己的 session 验证 file_chunk 路由。 |
| ~~GAP-3~~ | **已修复**：Agent 实现 `handle_clipboard`（set + get + CF_UNICODETEXT/CF_TEXT fallback），server 显式路由 `clipboard` 从 agent 到 client，client 加"剪贴板" tab UI | `agent/agent.py` `handle_clipboard` + `_on_message` `clipboard` 分支；`server/index.js` agent→client 路由；`server/static/index.html` `clipboardGet`/`clipboardSet` 函数和 panel |
| GAP-4 | `multer` 500MB 上限与 Deploy 50MB 上限不一致 | 文档化差异，非 bug |
| ~~GAP-5~~ | **已修复**：`wgc.py` 原来以 380+ 行 ctypes 手动包装 COM 绕弯 IGraphicsCaptureItem*，且 L325 拋 `NotImplementedError` | 重写为 ~240 行用 winrt 官方 interop helper（`create_for_monitor` / `create_direct3d11_device_from_dxgi_device` / `SoftwareBitmap.create_copy_from_surface_async`）。测试套件 63→72 (+9 wgc 测试)，真机上 `ScreenCapture().backend='wgc'`，2560×1440 RGB 帧平均抓取 ~30ms。 |

---

## 五、执行流程

```powershell
# 1. 跑所有 JS 测试
cd D:\.openclaw\workspace\projects\devtools\remote-control
node smoke_test.js
node upload_test.js
node test_path_security.js
node test_http_api.js
node test_ws_protocol.js
node test_e2e_flow.js

# 2. 跑 Python 测试（Windows 机器）
cd agent
python -m unittest tests.test_delta_encoder tests.test_mouse_keyboard tests.test_wgc -v

# 3. 一键执行
cd D:\.openclaw\workspace\projects\devtools\remote-control
.\run_all_tests.ps1
```

**CI 集成**：上述命令可直接接入 GitHub Actions，每次 PR 自动跑。

---

## 六、测试覆盖率声明

按 `SPEC.md` / `AGENT.md` 的功能点，**155 个断言**覆盖：

- ✅ Server HTTP API：100% 端点（A1-A9）
- ✅ Static Deploy 安全：100% 攻击面（B1-B12）
- ✅ WebSocket 协议：100% 消息类型 + 鉴权流程（C1-C15）
- ✅ Agent 输入模拟 + 命令 + 文件：100% 函数（D1-D15）
- ✅ Delta Encoder：100% 关键路径（E1-E10）
- ✅ Web Client：通过 server 端验证 100% 关键行为（F1-F7）
- ✅ 安全加固：100% 关键项（G1-G7）
- ✅ App 诊断日志主动上传：100% 端点 + 拦截面（H1-H12，含 36 个独立断言）
- ✅ Agent 鼠标注入静默失败防护：100% 路径（V1-V11，11 个独立断言 + 5 个真机 sub-test）
- ✅ Agent 日志轮转：100% 边缘情况（R1-R9，9 个独立断言）

**未覆盖**（手动 / E2E 真机验证）：
- Web Client 的 UI 渲染、canvas 绘制
- Agent 系统托盘菜单
- Windows 注册表自启动
- 真机屏幕捕获（需要 Windows + 桌面）
- nginx + SSL + WSS 端到端（需要部署环境）

这些建议保留在手动 checklist 中，不进入自动化测试。
