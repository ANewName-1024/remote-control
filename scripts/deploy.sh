#!/bin/bash
# Spring Cloud Demo - 自动化部署脚本
# 用法: ./deploy.sh [start|stop|restart|status|build]

set -e

# 配置
APP_NAME="springcloud-demo"
APP_DIR="/opt/${APP_NAME}"
VERSION="${1:-latest}"
BACKUP_DIR="${APP_DIR}/backup/$(date +%Y%m%d_%H%M%S)"

# 端口配置
EUREKA_PORT=8761
CONFIG_PORT=8082
USER_PORT=8081
GATEWAY_PORT=8080
OPS_PORT=8090

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 检查 root 权限
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 root 权限运行: sudo $0"
        exit 1
    fi
}

# 检查 Java
check_java() {
    if ! command -v java &> /dev/null; then
        log_error "Java 未安装"
        exit 1
    fi
    log_info "Java 版本: $(java -version 2>&1 | head -1)"
}

# 创建目录
create_dirs() {
    log_info "创建目录结构..."
    mkdir -p ${APP_DIR}/{app,config,logs,scripts,backup}
    mkdir -p ${BACKUP_DIR}
    
    # 创建日志目录
    mkdir -p /var/log/${APP_NAME}
    
    log_info "目录创建完成"
}

# 停止服务
stop_services() {
    log_info "停止旧服务..."
    for service in eureka-server gateway user-service config-service ops-service; do
        if pgrep -f "${service}" > /dev/null; then
            log_warn "停止 ${service}..."
            pkill -9 -f "${service}" || true
        fi
    done
    sleep 3
}

# 启动服务
start_services() {
    log_info "读取配置..."
    if [ ! -f "${APP_DIR}/config/env.conf" ]; then
        log_error "配置文件不存在: ${APP_DIR}/config/env.conf"
        exit 1
    fi
    
    source ${APP_DIR}/config/env.conf
    
    # 设置默认值
    : ${EUREKA_PORT:=8761}
    : ${CONFIG_PORT:=8082}
    : ${USER_PORT:=8081}
    : ${GATEWAY_PORT:=8080}
    : ${OPS_PORT:=8090}
    : ${ENABLE_OPS:=true}
    
    log_info "启动服务..."
    
    # 1. Eureka
    log_step "1/5 启动 Eureka Server (${EUREKA_PORT})..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Deureka.instance.hostname=${EUREKA_HOST:-localhost} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER:-admin}:${EUREKA_PASSWORD:-admin}@${EUREKA_HOST:-localhost}:${EUREKA_PORT}/eureka/ \
        -Dserver.port=${EUREKA_PORT} \
        ${APP_DIR}/app/eureka-server/*.jar \
        > /var/log/${APP_NAME}/eureka.log 2>&1 &
    
    sleep 10
    
    # 2. Config Service
    log_step "2/5 启动 Config Service (${CONFIG_PORT})..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Dspring.datasource.url=jdbc:postgresql://${DB_HOST:-localhost}:${DB_PORT:-5432}/${DB_NAME:-springcloud} \
        -Dspring.datasource.username=${DB_USER:-business} \
        -Dspring.datasource.password=${DB_PASSWORD:-business} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER:-admin}:${EUREKA_PASSWORD:-admin}@${EUREKA_HOST:-localhost}:${EUREKA_PORT}/eureka/ \
        -Dserver.port=${CONFIG_PORT} \
        ${APP_DIR}/app/config-service/*.jar \
        > /var/log/${APP_NAME}/config.log 2>&1 &
    
    sleep 5
    
    # 3. User Service
    log_step "3/5 启动 User Service (${USER_PORT})..."
    nohup java -jar \
        -Xms512m -Xmx1024m \
        -Dspring.datasource.url=jdbc:postgresql://${DB_HOST:-localhost}:${DB_PORT:-5432}/${DB_NAME:-springcloud} \
        -Dspring.datasource.username=${DB_USER:-business} \
        -Dspring.datasource.password=${DB_PASSWORD:-business} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER:-admin}:${EUREKA_PASSWORD:-admin}@${EUREKA_HOST:-localhost}:${EUREKA_PORT}/eureka/ \
        -DJWT_SECRET=${JWT_SECRET:-default-secret} \
        -Dserver.port=${USER_PORT} \
        ${APP_DIR}/app/user-service/*.jar \
        > /var/log/${APP_NAME}/user.log 2>&1 &
    
    sleep 5
    
    # 4. Gateway
    log_step "4/5 启动 Gateway (${GATEWAY_PORT})..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER:-admin}:${EUREKA_PASSWORD:-admin}@${EUREKA_HOST:-localhost}:${EUREKA_PORT}/eureka/ \
        -DJWT_SECRET=${JWT_SECRET:-default-secret} \
        -Dserver.port=${GATEWAY_PORT} \
        ${APP_DIR}/app/gateway/*.jar \
        > /var/log/${APP_NAME}/gateway.log 2>&1 &
    
    sleep 5
    
    # 5. Ops Service
    if [ "$ENABLE_OPS" = "true" ]; then
        log_step "5/5 启动 Ops Service (${OPS_PORT})..."
        nohup java -jar \
            -Xms256m -Xmx512m \
            -Deureka.client.service-url.defaultZone=http://${EUREKA_USER:-admin}:${EUREKA_PASSWORD:-admin}@${EUREKA_HOST:-localhost}:${EUREKA_PORT}/eureka/ \
            -Dserver.port=${OPS_PORT} \
            ${APP_DIR}/app/ops-service/*.jar \
            > /var/log/${APP_NAME}/ops.log 2>&1 &
    fi
    
    sleep 5
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    local services=(
        "Eureka:${EUREKA_PORT:-8761}"
        "Config:${CONFIG_PORT:-8082}"
        "User:${USER_PORT:-8081}"
        "Gateway:${GATEWAY_PORT:-8080}"
    )
    
    if [ "$ENABLE_OPS" = "true" ]; then
        services+=("Ops:${OPS_PORT:-8090}")
    fi
    
    local failed=0
    
    for service in "${services[@]}"; do
        local name="${service%%:*}"
        local port="${service##*:}"
        
        if nc -z localhost ${port} 2>/dev/null; then
            log_info "✓ ${name} (${port}) - OK"
        else
            log_error "✗ ${name} (${port}) - FAILED"
            failed=1
        fi
    done
    
    return $failed
}

# 查看状态
status() {
    echo ""
    echo "========================================"
    echo "  ${APP_NAME} 服务状态"
    echo "========================================"
    echo ""
    
    local services=(
        "Eureka Server:eureka-server:${EUREKA_PORT:-8761}"
        "Config Service:config-service:${CONFIG_PORT:-8082}"
        "User Service:user-service:${USER_PORT:-8081}"
        "Gateway:gateway:${GATEWAY_PORT:-8080}"
    )
    
    if [ "$ENABLE_OPS" = "true" ]; then
        services+=("Ops Service:ops-service:${OPS_PORT:-8090}")
    fi
    
    for service in "${services[@]}"; do
        local name="${service%%:*}"
        local process="${service%%:*}"
        local port="${service##*:}"
        
        if nc -z localhost ${port} 2>/dev/null; then
            echo -e "  ${GREEN}●${NC} ${name} (${port}) - 运行中"
        else
            echo -e "  ${RED}●${NC} ${name} (${port}) - 已停止"
        fi
    done
    
    echo ""
}

# 查看日志
logs() {
    local service="${1:-all}"
    
    if [ "$service" = "all" ]; then
        tail -f /var/log/${APP_NAME}/*.log
    else
        tail -f /var/log/${APP_NAME}/${service}.log
    fi
}

# 展示帮助
help() {
    echo "用法: $0 {start|stop|restart|status|logs|build|help}"
    echo ""
    echo "命令:"
    echo "  start     启动所有服务"
    echo "  stop      停止所有服务"
    echo "  restart   重启所有服务"
    echo "  status    查看服务状态"
    echo "  logs      查看日志 (Usage: $0 logs [service])"
    echo "  build     编译项目"
    echo "  help      显示帮助"
    echo ""
    echo "示例:"
    echo "  sudo $0 start"
    echo "  sudo $0 status"
    echo "  sudo $0 logs gateway"
}

# 主流程
main() {
    case "${1:-help}" in
        start)
            check_root
            check_java
            create_dirs
            stop_services
            start_services
            health_check
            log_info "部署完成!"
            ;;
        stop)
            check_root
            stop_services
            log_info "服务已停止"
            ;;
        restart)
            check_root
            stop_services
            sleep 3
            start_services
            health_check
            log_info "重启完成!"
            ;;
        status)
            status
            ;;
        logs)
            logs "${2:-all}"
            ;;
        build)
            log_info "编译项目..."
            mvn clean package -DskipTests
            log_info "编译完成!"
            ;;
        help|*)
            help
            ;;
    esac
}

main "$@"
