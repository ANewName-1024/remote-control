#!/usr/bin/env bash
# VPS-side installer. Run via: ssh root@host 'bash -s' < vps-install.sh
# Idempotent: safe to re-run on existing deployment.

set -euo pipefail

APP_DIR="/opt/remote-control"
SERVER_DIR="$APP_DIR/server"
SERVICE="remote-control"

log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || fail "must run as root"

# 0. Pre-flight
command -v node >/dev/null 2>&1 || fail "node not installed"
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]')
[[ "$NODE_MAJOR" -ge 18 ]] || fail "node >= 18 required (got $(node -v))"
command -v systemctl >/dev/null 2>&1 || fail "systemctl not found"

# 1. Stop existing service (if any) so we can swap files
if systemctl is-active --quiet "$SERVICE"; then
    log "stopping existing $SERVICE"
    systemctl stop "$SERVICE"
fi

# 2. Extract tarball (if provided via stdin or $1)
TARBALL="${1:-/tmp/remote-control-server.tar.gz}"
[[ -f "$TARBALL" ]] || fail "tarball not found at $TARBALL"

log "extracting $TARBALL -> $APP_DIR"
mkdir -p "$APP_DIR"
tar -xzf "$TARBALL" -C "$APP_DIR"

# 3. Install production deps
log "npm ci --omit=dev"
cd "$SERVER_DIR"
npm ci --omit=dev 2>&1 | tail -10

# 4. Verify .env
[[ -f .env ]] || fail ".env not found at $SERVER_DIR/.env"
set -a; source .env; set +a
[[ -n "${PORT:-}" ]]        || fail "PORT missing in .env"
[[ -n "${ACCESS_PASSWORD:-}" ]] || fail "ACCESS_PASSWORD missing in .env"
log ".env ok (PORT=$PORT)"

# 5. Uploads dir (writable by Node)
mkdir -p "$SERVER_DIR/uploads"
chown -R root:root "$APP_DIR" 2>/dev/null || true

# 6. Install systemd unit
log "installing systemd unit"
install -m 0644 /opt/remote-control/deploy/remote-control.service /etc/systemd/system/remote-control.service
systemctl daemon-reload
systemctl enable "$SERVICE"

# 7. Start
log "starting $SERVICE"
systemctl restart "$SERVICE"

# 8. Health check
sleep 2
if systemctl is-active --quiet "$SERVICE"; then
    log "service active"
else
    warn "service failed to start; recent logs:"
    journalctl -u "$SERVICE" --no-pager -n 30
    fail "service did not start"
fi

# 9. Quick HTTP probe
if command -v curl >/dev/null 2>&1; then
    log "probing http://127.0.0.1:$PORT/"
    if curl -fsS -o /dev/null -w 'status=%{http_code}\n' "http://127.0.0.1:$PORT/"; then
        log "OK — relay responding on port $PORT"
    else
        warn "relay not responding (nginx may proxy from 9080/8443)"
    fi
fi

log "deploy complete"
log "  status:  systemctl status $SERVICE"
log "  logs:    journalctl -u $SERVICE -f"
log "  nginx:   9080 / 8443 should now relay to localhost:$PORT"
