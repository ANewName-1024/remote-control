# DEBUGGING.md

> 真实排过 + 验证过的故障场景。多数问题用一句 PowerShell / Python 命令定位。

## 1. 抓屏 `拒绝访问` / `E_ACCESSDENIED`

**根因**：机器在锁屏状态（Windows 故意阻止 GDI/DXGI 访问保护密码输入）

**快速诊断**：
```powershell
# 查 LogonUI 进程（锁屏 = 一定有它）
Get-Process LogonUI -ErrorAction SilentlyContinue

# 查最后输入时间
([System.Windows.Forms.SystemInformation]::UserIdleTime 2>$null).TotalHours

# 查 OpenInputDesktop
powershell -Command "Add-Type -Name U -Namespace W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern System.IntPtr OpenInputDesktop(uint a, uint b, uint c);'; [W.U]::OpenInputDesktop(0, 0, 0)"
# 返回 0 = 没 input desktop（锁屏 / 无用户登录）
# 返回非 0 = 有 input desktop
```

**解决**：
- A) 物理解锁电脑
- B) 关锁屏（适合专用机）：`powercfg /change monitor-timeout-ac 0` + gpedit 关屏保
- C) **加 WGC UWP 后端**（`capture.py` TODO；不会做架构层突破但能拿到锁屏时的合法路径）

**DXGI 在锁屏下也被拒**——已实测 `dxcam.create() → COMError: E_ACCESSDENIED`。不要重复踩坑。

## 2. helper 不启动

```powershell
# 看 service 日志
Get-Content "$env:APPDATA\RemoteControlAgent\logs\agent.log" -Tail 50

# 常见 3 个原因
```

| 日志关键字 | 原因 | 修法 |
|------------|------|------|
| `WTSQueryUserToken failed` | 没用户登录或 WTS API 失败 | 确认有 active session 1 |
| `DuplicateTokenEx failed: 5` | 缺 `SeTcbPrivilege`（service 账号需要） | 用 LocalSystem 跑；Local Service 不行 |
| `CreateProcessAsUserW failed: 5` | lpDesktop 不是 'Default' 或 env block 缺 RC_HELPER_TOKEN | 检查 service.py 的 startupinfo 和 env |

## 3. service 报 "token mismatch"

helper 收到的 `RC_HELPER_TOKEN` 和 service 生成的不一致。

```python
# service 启动时打印 token（DEBUG 用）
log.info(f'auth token = {AUTH_TOKEN}')
```

```powershell
# helper 端拿 token
$env:RC_HELPER_TOKEN  # 应该跟 service 一样
```

如果不一致：service 用 `secrets.token_urlsafe(32)` 生成后没传过去，或 env block 在 `CreateProcessAsUserW` 时被截断。

## 4. 命名管道 "all instances are busy"

`nMaxInstances=1` 的管道被前一个连接占着。新连接 `CreateNamedPipe` 失败。

**修法**：用 `win32pipe.PIPE_UNLIMITED_INSTANCES`，每个连接 close 后 _pipe_thread 创建新实例（见 `service.py`）。

**如果还有此错**：重启 service（泄漏了 `cmd_conn` / `frame_conn`）。

## 5. 管道 ReadFile 永远返回 0

**症状**：helper 发了数据，service `PeekNamedPipe` 永远返回 0。

**根因**（已踩）：`PIPE_TYPE_MESSAGE` 模式下 `ReadFile(h, N)` 返回整条 message（不管 N），`_read_exact` 用 `n - len(buf)` 算成负数。

**修法**：用 `PIPE_BYTE_STREAM`（默认）+ 长度前缀 framing。`agent/service.py` 已用此模式。

## 6. WebSocket 断连

| 症状 | 检查 |
|------|------|
| 每 30s 断 | VPS 端 nginx proxy_read_timeout 太小 |
| 立即 401 | ACCESS_PASSWORD 不一致 |
| 立即 1006 | VPS relay 没启动或端口被封（`curl http://8.137.116.121:21112/` 测一下） |

## 7. 输入无响应

```powershell
# helper 在哪个 session？
& python -c "from ctypes import *; import ctypes; GetCurrentProcessId = ctypes.windll.kernel32.GetCurrentProcessId; print('pid', GetCurrentProcessId())"
# 然后：
Get-CimInstance Win32_Process -Filter "ProcessId = <pid>" | Select Name, SessionId
```

Session 0 = SYSTEM（不能注入）  
Session 1+ = 用户桌面（应该正常）  
Session 0xFFFFFFFF = 没人登录

如果 helper 在 Session 0：`WTSQueryUserToken` 没拿到 user token（看 §2 排查）。

## 8. venv pip install 被全局劫持

```powershell
# 报错：依赖装到了 D:\PythonPackages 而不是 venv
& "venv\Scripts\python.exe" -m pip install foo
```

**根因**：`pip config set global.target D:\PythonPackages`（AGENT.md 里说要在 D 盘装 Python 包，但 venv 不该受影响）

**修法**：
```powershell
& "venv\Scripts\python.exe" -m pip install --target="venv\Lib\site-packages" foo
# 显式 --target 绕过全局配置
```

或者：
```powershell
# 清掉全局 target（venv 不再被劫持）
pip config unset global.target
# 然后正常 pip install
```

## 9. systemd "Warning: unit file changed"

deploy 脚本重新 daemon-reload 时，systemd 提示这个不算错。

但如果 PS 脚本 `ErrorActionPreference = 'Stop'`，**这个 native stderr 会让脚本终止**。解法：
```powershell
$oldPref = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
ssh ... 2>&1 | Out-Null  # 把 stderr 吃掉
$ErrorActionPreference = $oldPref
```

## 10. vps-install 部署成功但 deploy 脚本 exit 1

**根因**（已踩）：`Invoke-Remote` 函数同时 `Write-Output` 输出和返回 exit code，PS 把 `[array]` 当 `$false`。

**修法**（已用 commit 5d341f0）：
- `Invoke-Remote` 用 `Out-Host` 替代 `Write-Output`（host 不进 return stream）
- 调用 native 命令时临时 `ErrorActionPreference = 'SilentlyContinue'`

## 11. CONTEXT 长了 / 跑了很久不响应

OpenClaw session token 上限 200k。如果感觉卡：
```bash
/compact  # 手动压缩
# 或 /new 开新 session（MEMORY.md 会接力）
```

## 12. 已知未做（roadmap）

- [ ] `read_frame` 帧读取在 PIPE_BYTE_STREAM 下 TODO（独立 PR）
- [ ] WGC UWP 抓屏后端（解锁锁屏）
- [ ] install-windows-agent.ps1 双进程版
- [ ] WebSocket ↔ helper 桥接
- [ ] 完整的端到端实测（service 可达 + helper 抓帧 + WS 推流 + 客户端解码）


---

## WGC (Windows.Graphics.Capture) UWP 实现状态 (2026-06-02)

### 进展

| 阶段 | 状态 | commit |
|------|------|--------|
| IID 找对（3628E81B-3CAC-4C60-B7F4-**23CE0E0C3356**）| ✅ | 本次 session |
| COM apartment init + HSTRING | ✅ | 本次 session |
| RoGetActivationFactory + QI IID_IGraphicsCaptureItemInterop | ✅ | 本次 session |
| CreateForMonitor **3-arg 签名**（HMONITOR + REFIID + void\*\*）| ✅ | 本次 session |
| Wrap IGraphicsCaptureItem* 为 winrt 对象 | ❌ | — |
| Direct3D11CaptureFramePool / Session ctypes 实现 | ❌ | — |
| 帧 surface readback（D3D11 staging texture）| ❌ | — |
| 锁屏实测 | ❌ | 需解锁后 |

### 关键调试发现

#### 1. IID 末尾是 33 56 不是 2A 54

网上资料经常贴错（甚至 Microsoft Learn 示例）。`Windows.Graphics.Capture.Interop.h`（SDK build 26100）实际定义：
```c
DECLARE_INTERFACE_IID_(IGraphicsCaptureItemInterop, IUnknown,
    "3628E81B-3CAC-4C60-B7F4-23CE0E0C3356")
```
**2A 54 会导致 E_NOINTERFACE**（QI 失败，但 RoGetActivationFactory 本身能跑通）。调试时务必看真 SDK header。

#### 2. CreateForMonitor 是 3-arg 不是 5-arg

新 Windows 10/11 上是：
```c
HRESULT CreateForMonitor(HMONITOR monitor, REFIID riid, void **result);
```
**不是** 5-arg 版本（带 D3D11 device）。D3D11 device 由系统隐式绑定。传多了 arg 会 E_INVALIDARG。

#### 3. RoGetActivationFactory 要 HSTRING 不接 wchar_p

```python
WindowsCreateString(class_name, len(class_name), &hstring)
RoGetActivationFactory(hstring.value, IID, &factory)  # 用 hstring.value 不是 wchar_p
```
不转 HSTRING 会 E_INVALIDARG。

#### 4. winrt-python 3.2.1 不暴露 CreateForMonitor 静态方法

`GraphicsCaptureItem.create_for_monitor` 不存在。只能走 `RoGetActivationFactory + QI + IGraphicsCaptureItemInterop::CreateForMonitor` COM 路径。

#### 5. c_void_p argtype 是必须的（不要省）

不设 `RoGetActivationFactory.argtypes` -> 64-bit HSTRING overflow 到 32-bit register -> ctypes ArgumentError。设了 ctypes 才能正确 marshal 64-bit handle。

### 已知坑（仍未解决）

#### winrt.GraphicsCaptureItem._from 只接 1 个 arg
`GraphicsCaptureItem._from(p_item.value)` -> "takes exactly one argument (2 given)"。
`Object(ptr)` -> "cannot create 'Object' instances"。
没有 public API 从 raw `IGraphicsCaptureItem*` 创建 winrt 包装对象。

**workaround 候选**：
- a) 写 comtypes 接口定义，从 raw pointer 创建 COM wrapper（200 行）
- b) 整个 WGC 栈用 ctypes 实现，绕过 winrt-python（300+ 行）
- c) 等 winrt-python 升级到支持 `_from(ptr, iid)` 双参版本

### 现状

`agent/wgc.py` 已能：
- ✅ 编译（import 不出错）
- ✅ 跑 D3D11 device init
- ✅ 跑 HSTRING + RoGetActivationFactory + QI + CreateForMonitor（拿到 IGraphicsCaptureItem* 指针）
- ❌ wrap 失败 -> 抛 `NotImplementedError` -> capture.py fall through 到 dxcam/mss/PIL

**未完工**。建议下次 session 选 (a) 或 (b) 方案补完 4-6 小时工作量。

### 验证

```powershell
# 确认 WGC_AVAILABLE=True（所有依赖装好）
& "$env:APPDATA\RemoteControlAgent\venv\Scripts\python.exe" -c "from agent.wgc import WGC_AVAILABLE; print(WGC_AVAILABLE)"
# True

# 确认 ScreenCapture 还能 fall through
& "$env:APPDATA\RemoteControlAgent\venv\Scripts\python.exe" -c "from agent.capture import ScreenCapture; c = ScreenCapture(); print(c.backend, c.width, c.height)"
# mss 2560x1440（WGC init 抛 NotImplementedError -> fall through 到 mss）

# 跑 WGC 框架 smoke test
& "$env:APPDATA\RemoteControlAgent\venv\Scripts\python.exe" -m unittest tests.test_wgc -v
# Ran 4 tests in 0.3s OK
```
