# Remote-Control Deployment

Two targets, two scripts:

| Target | Host | Script | Process manager |
|---|---|---|---|
| **Server** (Node.js relay) | VPS `8.137.116.121:2222` (nginx 9080/8443 → relay 21112) | `deploy-vps.ps1` (Windows) → `vps-install.sh` (VPS) | systemd |
| **Agent** (Python automation) | Windows host | `install-windows-agent.ps1` | nssm + Windows Service |

## Quick start

### 1. Configure secrets

```powershell
# VPS server env (PORT, ACCESS_PASSWORD, etc.)
cp deploy\.env.vps.example deploy\.env.vps
notepad deploy\.env.vps
# → edit ACCESS_PASSWORD (32+ char hex)

# Windows agent env (WS_URL, ACCESS_PASSWORD, AGENT_ID)
cp deploy\.env.windows.example deploy\.env.windows
notepad deploy\.env.windows
# → edit WS_URL, ACCESS_PASSWORD (must match server!), AGENT_ID
```

**ACCESS_PASSWORD must be identical on both sides** — it's the shared HMAC secret.

### 2. Deploy VPS

```powershell
cd D:\.openclaw\workspace\projects\devtools\remote-control
pwsh ./deploy/deploy-vps.ps1
```

This will:
1. `build-tar.ps1` — packages `server/` + `deploy/` into `deploy\dist\remote-control-server-<ts>.tar.gz`
2. SCP tarball + `.env` + `remote-control.service` to VPS
3. SSHes in and runs `vps-install.sh`:
   - extracts tarball to `/opt/remote-control`
   - `npm ci --omit=dev` in `server/`
   - installs systemd unit, `enable --now`
   - probes `http://127.0.0.1:21112/`

### 3. Deploy Windows Agent

```powershell
pwsh ./deploy/install-windows-agent.ps1
```

This will:
1. copy `.env` → `%APPDATA%\RemoteControlAgent\agent.env`
2. create venv at `%APPDATA%\RemoteControlAgent\venv\`
3. `pip install -r agent\requirements.txt`
4. download nssm if missing, register Windows Service `RemoteControlAgent`
5. start the service

### 4. Verify

```powershell
# On VPS:
ssh -p 2222 -i %USERPROFILE%\.ssh\id_rsa_vps root@8.137.116.121 \
  'systemctl status remote-control; journalctl -u remote-control -n 50 --no-pager'

# On Windows:
Get-Service RemoteControlAgent
Get-Content $env:APPDATA\RemoteControlAgent\agent_stderr.log -Tail 30
```

## Idempotency

- `deploy-vps.ps1` is safe to re-run (replaces files, restarts service).
- `install-windows-agent.ps1` removes any prior `RemoteControlAgent` service and recreates it.
- The venv is reused (only created if missing).

## Rollback

```powershell
# On VPS:
ssh -p 2222 root@8.137.116.121 'systemctl stop remote-control; rm -rf /opt/remote-control.old'
# (next deploy keeps /opt/remote-control.old as backup if you add it)
```

```powershell
# On Windows:
sc.exe delete RemoteControlAgent
Remove-Item -Recurse $env:APPDATA\RemoteControlAgent
```

## Files in this directory

| File | Purpose |
|---|---|
| `build-tar.ps1` | tar.gz packager (runs locally) |
| `deploy-vps.ps1` | one-shot VPS deploy |
| `vps-install.sh` | VPS-side installer (systemd + npm) |
| `remote-control.service` | systemd unit template |
| `.env.vps.example` | server env template |
| `install-windows-agent.ps1` | one-shot Windows Agent install |
| `.env.windows.example` | agent env template |
| `README.md` | this file |
