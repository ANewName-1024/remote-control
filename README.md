# 远程控制系统

一套自建的远程控制方案，支持从安卓浏览器直接控制 Windows 电脑。

**核心特点：**
- 🌐 纯 Web 界面，无需安装任何 App（安卓浏览器即可）
- 🔒 Windows Agent 主动连接云服务器（outbound），无需端口映射
- 💻 全功能：屏幕查看、鼠标键盘控制、命令执行、文件传输

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ┌──────────┐     HTTPS/WSS      ┌──────────────────┐  │
│  │ Android  │◄──────────────────►│  Cloud VPS        │  │
│  │ Browser  │                    │  (Node.js Relay)  │  │
│  └──────────┘                    │                   │  │
│                                  │  • Web 控制台     │  │
│                                  │  • WebSocket 路由 │  │
│                                  │  • 文件中转       │  │
└──────────────────────────────────│──────────────────│──┘
                                    └───────▲──────────┘
                                              │
                                       outbound WS
                                              │
                                    ┌─────────┴────────┐
                                    │  Windows Agent    │
                                    │  (Python)         │
                                    │  • 屏幕捕获       │
                                    │  • 输入模拟       │
                                    │  • 命令执行       │
                                    │  • 文件传输       │
                                    └──────────────────┘
```

---

## 快速部署

### 第一步：云服务器（VPS）

最低配置：1核 1G 内存，推荐 2G 以上（用于中转大文件）

```bash
# 1. 安装 Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo bash -
sudo apt install nodejs

# 2. 下载服务端
git clone <your-repo>
cd remote-control/server
npm install

# 3. 启动（生产环境建议用 systemd 或 pm2）
#    ACCESS_PASSWORD: 服务器访问密码（必填）
#    PORT: 监听端口（默认 21112）
ACCESS_PASSWORD='你的密码' PORT=21112 node index.js
```

**推荐：使用 Nginx 反向代理 + SSL**
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:21112;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 第二步：Windows Agent

```powershell
# 1. 安装 Python 3.8+
# 下载: https://www.python.org/downloads/

# 2. 安装依赖（管理员权限运行 PowerShell）
cd remote-control/agent
pip install -r requirements.txt

# 3. 设置服务器地址（改为你的 VPS IP 或域名）
$env:RC_SERVER = "ws://你的服务器IP:21112"

# 4. 运行 Agent
python agent.py
```

运行后会显示：
```
Agent ID:  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Secret:    abcdefgh12345678
```

**把 Agent ID 和 Secret 记录下来，用于连接。**

### 第三步：安卓访问

1. 打开浏览器，访问 `https://你的服务器IP`
2. 点击「连接」，输入 Agent ID
3. 输入 Secret（Agent 端显示的密钥）
4. 开始控制！

---

## 功能说明

### 屏幕控制
- 鼠标点击、拖拽、滚轮
- 触摸手势（移动端）
- 缩放：50% - 300%

### 快捷键
- Ctrl+Alt+Del、Alt+Tab、Win 键
- Alt+F4 关闭窗口

### 终端
- 直接在浏览器执行 CMD/PowerShell 命令
- 支持中文输出
- 命令历史

### 文件传输
- 从 Windows 下载文件到本地
- 从本地上传文件到 Windows
- 大文件自动分块

---

## 安全建议

1. **更换 Secret**：Agent 的 secret 是自动生成的，生产环境建议定期更换
2. **防火墙**：只开放 443 端口
3. **Agent 权限**：Agent 以当前用户权限运行，不要用管理员运行
4. **HTTPS**：必须使用 HTTPS，否则浏览器不允许 WebSocket

---

## 目录结构

```
remote-control/
├── server/                    # 云服务器端 (Node.js)
│   ├── package.json
│   ├── index.js              # 主入口
│   └── static/               # Web 控制台
│       └── index.html
├── agent/                    # Windows Agent (Python)
│   ├── agent.py              # 主程序
│   └── requirements.txt      # Python 依赖
├── SPEC.md                   # 设计规范
└── README.md
```

---

## 一键打包 Windows Agent（可选）

用 PyInstaller 将 Agent 打包成单个 exe：

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole --name RemoteControlAgent agent.py
```

生成的 exe 在 `dist/RemoteControlAgent.exe`，可以分发给其他 Windows 机器。
