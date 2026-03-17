#!/bin/bash
# upgrade.sh - 滚动升级脚本

set -e

VERSION="$1"
APP_NAME="springcloud-demo"
APP_DIR="/opt/${APP_NAME}"
BACKUP_DIR="${APP_DIR}/backup"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查参数
if [ -z "$VERSION" ]; then
    echo "用法: $0 <版本号>"
    echo "示例: $0 v1.1.0"
    exit 1
fi

log_info "开始升级到版本: $VERSION"

# 1. 创建备份
log_info "备份当前版本..."
BACKUP_TARGET="${BACKUP_DIR}/$(date +%Y%m%d_%H%M%S)_${VERSION}"
mkdir -p ${BACKUP_TARGET}

if [ -d "${APP_DIR}/app" ]; then
    cp -r ${APP_DIR}/app/* ${BACKUP_TARGET}/
    log_info "备份保存到: ${BACKUP_TARGET}"
else
    log_warn "未找到应用目录，跳过备份"
fi

# 2. 滚动升级
log_info "开始滚动升级..."

# 2.1 停止 Gateway (入口)
log_info "停止 Gateway..."
pkill -f "gateway" || true
sleep 3

# 2.2 升级 User Service
log_info "升级 User Service..."
pkill -f "user-service" || true
sleep 3
# 在此添加部署新版本 JAR 的命令
# cp target/user-service-*.jar ${APP_DIR}/app/user-service/
# nohup java -jar ${APP_DIR}/app/user-service/*.jar &

# 等待服务启动
sleep 5

# 验证
if curl -sf http://localhost:8081/actuator/health > /dev/null 2>&1; then
    log_info "✓ User Service 启动成功"
else
    log_warn "✗ User Service 启动失败"
fi

# 2.3 升级 Config Service
log_info "升级 Config Service..."
pkill -f "config-service" || true
sleep 3

sleep 5

# 2.4 启动 Gateway
log_info "启动 Gateway..."
# nohup java -jar ${APP_DIR}/app/gateway/*.jar &

sleep 5

# 2.5 验证整体
if curl -sf http://localhost:8080/actuator/health > /dev/null 2>&1; then
    log_info "✓ Gateway 启动成功"
else
    log_warn "✗ Gateway 启动失败"
fi

log_info "升级完成!"
echo ""
log_info "如需回滚，执行: $0 rollback ${BACKUP_TARGET}"
