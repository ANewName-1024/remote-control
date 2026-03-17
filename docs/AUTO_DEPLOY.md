# 自动化部署、升级与卸载方案

## 概述

本文档描述 Spring Cloud Demo 项目的自动化部署、升级和卸载方案，支持多种部署模式：传统 VM、Docker、Kubernetes。

---

## 1. 架构设计

### 1.1 部署架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        部署服务器 (CI/CD)                         │
├─────────────────────────────────────────────────────────────────┤
│  GitLab CI / GitHub Actions / Jenkins                          │
│  - 代码拉取                                                    │
│  - 编译构建                                                    │
│  - 单元测试                                                    │
│  - 镜像构建                                                    │
│  - 部署推送                                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        目标环境                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ VM 部署     │  │ Docker      │  │ K8s        │           │
│  │ (传统模式)   │  │ (Compose)   │  │ (生产推荐)  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 服务依赖关系

```
启动顺序:
1. Eureka (8761) - 服务注册中心
   ↓
2. Config Service (8082) - 配置中心
   ↓
3. User Service (8081) - 用户服务
   ↓
4. Gateway (8080) - API 网关
   ↓
5. Ops Service (8090) - 运维服务 (可选)
```

---

## 2. VM 部署方案

### 2.1 目录结构

```
/opt/springcloud-demo/
├── app/                    # 应用 JAR 包
│   ├── eureka-server/
│   ├── gateway/
│   ├── user-service/
│   ├── config-service/
│   └── ops-service/
├── config/                 # 配置文件
│   ├── application.yml
│   └── application-prod.yml
├── logs/                   # 日志目录
├── scripts/                # 脚本目录
│   ├── deploy.sh         # 部署脚本
│   ├── upgrade.sh        # 升级脚本
│   └── uninstall.sh      # 卸载脚本
└── backup/                # 备份目录
```

### 2.2 部署脚本

```bash
#!/bin/bash
# deploy.sh - 自动化部署脚本

set -e

# 配置
APP_NAME="springcloud-demo"
APP_DIR="/opt/${APP_NAME}"
VERSION="${1:-latest}"
BACKUP_DIR="${APP_DIR}/backup/$(date +%Y%m%d_%H%M%S)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 root 权限
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用 root 权限运行"
        exit 1
    fi
}

# 创建目录结构
create_dirs() {
    log_info "创建目录结构..."
    mkdir -p ${APP_DIR}/{app,config,logs,scripts,backup}
    mkdir -p ${APP_DIR}/app/{eureka-server,gateway,user-service,config-service,ops-service}
    mkdir -p ${BACKUP_DIR}
}

# 停止旧服务
stop_services() {
    log_info "停止旧服务..."
    for service in eureka-server gateway user-service config-service ops-service; do
        if pgrep -f "${service}" > /dev/null; then
            log_warn "停止 ${service}..."
            pkill -f "${service}" || true
        fi
    done
    sleep 5
}

# 启动服务
start_services() {
    log_info "启动服务..."
    
    # 读取配置
    source ${APP_DIR}/config/env.conf
    
    # 1. 启动 Eureka
    log_info "启动 Eureka Server..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Deureka.instance.hostname=${EUREKA_HOST} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER}:${EUREKA_PASSWORD}@${EUREKA_HOST}:${EUREKA_PORT}/eureka/ \
        -Dserver.port=${EUREKA_PORT} \
        ${APP_DIR}/app/eureka-server/*.jar \
        > ${APP_DIR}/logs/eureka.log 2>&1 &
    
    sleep 10
    
    # 2. 启动 Config Service
    log_info "启动 Config Service..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Dspring.datasource.url=jdbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME} \
        -Dspring.datasource.username=${DB_USER} \
        -Dspring.datasource.password=${DB_PASSWORD} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER}:${EUREKA_PASSWORD}@${EUREKA_HOST}:${EUREKA_PORT}/eureka/ \
        -Dserver.port=${CONFIG_PORT} \
        ${APP_DIR}/app/config-service/*.jar \
        > ${APP_DIR}/logs/config.log 2>&1 &
    
    sleep 5
    
    # 3. 启动 User Service
    log_info "启动 User Service..."
    nohup java -jar \
        -Xms512m -Xmx1024m \
        -Dspring.datasource.url=jdbc:postgresql://${DB_HOST}:${DB_PORT}/${DB_NAME} \
        -Dspring.datasource.username=${DB_USER} \
        -Dspring.datasource.password=${DB_PASSWORD} \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER}:${EUREKA_PASSWORD}@${EUREKA_HOST}:${EUREKA_PORT}/eureka/ \
        -DJWT_SECRET=${JWT_SECRET} \
        -Dserver.port=${USER_PORT} \
        ${APP_DIR}/app/user-service/*.jar \
        > ${APP_DIR}/logs/user.log 2>&1 &
    
    sleep 5
    
    # 4. 启动 Gateway
    log_info "启动 Gateway..."
    nohup java -jar \
        -Xms256m -Xmx512m \
        -Deureka.client.service-url.defaultZone=http://${EUREKA_USER}:${EUREKA_PASSWORD}@${EUREKA_HOST}:${EUREKA_PORT}/eureka/ \
        -DJWT_SECRET=${JWT_SECRET} \
        -Dserver.port=${GATEWAY_PORT} \
        ${APP_DIR}/app/gateway/*.jar \
        > ${APP_DIR}/logs/gateway.log 2>&1 &
    
    sleep 5
    
    # 5. 启动 Ops Service (可选)
    if [ "$ENABLE_OPS" = "true" ]; then
        log_info "启动 Ops Service..."
        nohup java -jar \
            -Xms256m -Xmx512m \
            -Deureka.client.service-url.defaultZone=http://${EUREKA_USER}:${EUREKA_PASSWORD}@${EUREKA_HOST}:${EUREKA_PORT}/eureka/ \
            -Dserver.port=${OPS_PORT} \
            ${APP_DIR}/app/ops-service/*.jar \
            > ${APP_DIR}/logs/ops.log 2>&1 &
    fi
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    local services=(
        "Eureka:${EUREKA_PORT}"
        "Config:${CONFIG_PORT}"
        "User:${USER_PORT}"
        "Gateway:${GATEWAY_PORT}"
    )
    
    if [ "$ENABLE_OPS" = "true" ]; then
        services+=("Ops:${OPS_PORT}")
    fi
    
    for service in "${services[@]}"; do
        local name="${service%%:*}"
        local port="${service##*:}"
        
        if nc -z localhost ${port} 2>/dev/null; then
            log_info "✓ ${name} (${port}) - OK"
        else
            log_error "✗ ${name} (${port}) - FAILED"
        fi
    done
}

# 主流程
main() {
    check_root
    create_dirs
    stop_services
    start_services
    health_check
    
    log_info "部署完成!"
}

main "$@"
```

### 2.3 配置文件

```bash
# config/env.conf
# 环境配置

# Eureka
EUREKA_HOST=localhost
EUREKA_PORT=8761
EUREKA_USER=admin
EUREKA_PASSWORD=Eureka@2024

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=springcloud
DB_USER=business
DB_PASSWORD=Business@123

# JWT
JWT_SECRET=your-secret-key-here

# Ports
EUREKA_PORT=8761
CONFIG_PORT=8082
USER_PORT=8081
GATEWAY_PORT=8080
OPS_PORT=8090

# Options
ENABLE_OPS=true
```

---

## 3. 升级方案

### 3.1 滚动升级

```bash
#!/bin/bash
# upgrade.sh - 滚动升级脚本

set -e

VERSION="$1"
BACKUP_DIR="/opt/springcloud-demo/backup"

log_info "开始升级到版本: $VERSION"

# 1. 备份当前版本
log_info "备份当前版本..."
mkdir -p ${BACKUP_DIR}/$(date +%Y%m%d_%H%M%S)
cp -r /opt/springcloud-demo/app/* ${BACKUP_DIR}/

# 2. 停止 Gateway (入口服务)
log_info "停止 Gateway..."
pkill -f "gateway"

# 3. 升级 User Service
log_info "升级 User Service..."
pkill -f "user-service"
# 部署新版本
# ...

# 4. 启动 User Service
# ...

# 5. 验证 User Service
curl -f http://localhost:8081/actuator/health || exit 1

# 6. 升级 Config Service
# ...

# 7. 启动 Gateway
# ...

# 8. 验证整体
curl -f http://localhost:8080/actuator/health

log_info "升级完成!"
```

### 3.2 版本回滚

```bash
#!/bin/bash
# rollback.sh - 版本回滚脚本

VERSION="$1"

if [ -z "$VERSION" ]; then
    echo "用法: $0 <版本号>"
    exit 1
fi

BACKUP_DIR="/opt/springcloud-demo/backup/${VERSION}"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "版本 $VERSION 不存在"
    exit 1
fi

echo "回滚到版本: $VERSION"

# 停止服务
pkill -f "springcloud-demo"

# 恢复文件
cp -r ${BACKUP_DIR}/* /opt/springcloud-demo/app/

# 重新部署
/opt/springcloud-demo/scripts/deploy.sh

echo "回滚完成!"
```

---

## 4. 卸载方案

### 4.1 卸载脚本

```bash
#!/bin/bash
# uninstall.sh - 完整卸载脚本

set -e

APP_NAME="springcloud-demo"
APP_DIR="/opt/${APP_NAME}"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 确认
echo "========================================"
echo "  警告: 此操作将完全卸载 ${APP_NAME}"
echo "========================================"
read -p "确认继续? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "取消卸载"
    exit 0
fi

# 1. 停止所有服务
log_info "停止所有服务..."
for service in eureka-server gateway user-service config-service ops-service; do
    pkill -f "${service}" || true
done

# 2. 删除应用目录
log_info "删除应用目录..."
rm -rf ${APP_DIR}

# 3. 删除日志
log_info "删除日志..."
rm -rf /var/log/${APP_NAME}

# 4. 删除用户 (如果创建)
log_info "删除系统用户..."
userdel ${APP_NAME} 2>/dev/null || true

# 5. 删除定时任务
log_info "删除定时任务..."
crontab -r 2>/dev/null || true

# 6. 清理防火墙规则 (可选)
log_warn "如需清理防火墙规则，请手动执行:"

echo ""
echo "========================================"
echo "  卸载完成!"
echo "========================================"
echo ""
echo "手动清理项:"
echo "  1. 数据库: DROP DATABASE ${APP_NAME};"
echo "  2. 防火墙: ufw delete allow <port>"
echo "  3. Nginx:  remove config from /etc/nginx/"
```

---

## 5. Docker Compose 部署

### 5.1 docker-compose.yml

```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  postgres:
    image: postgres:15-alpine
    container_name: springcloud-postgres
    environment:
      POSTGRES_DB: springcloud
      POSTGRES_USER: business
      POSTGRES_PASSWORD: Business@123
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U business"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Eureka 注册中心
  eureka:
    build: ./eureka-server
    container_name: springcloud-eureka
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - SERVER_PORT=8761
    ports:
      - "8761:8761"
    depends_on:
      postgres:
        condition: service_healthy

  # Config 配置中心
  config:
    build: ./config-service
    container_name: springcloud-config
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - SERVER_PORT=8082
      - EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=http://eureka:8761/eureka/
    ports:
      - "8082:8082"
    depends_on:
      - eureka

  # User 用户服务
  user:
    build: ./user-service
    container_name: springcloud-user
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - SERVER_PORT=8081
      - EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=http://eureka:8761/eureka/
    ports:
      - "8081:8081"
    depends_on:
      - eureka
      - config

  # Gateway 网关
  gateway:
    build: ./gateway
    container_name: springcloud-gateway
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - SERVER_PORT=8080
      - EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=http://eureka:8761/eureka/
    ports:
      - "8080:8080"
    depends_on:
      - eureka
      - user

  # Ops 运维服务
  ops:
    build: ./ops-service
    container_name: springcloud-ops
    environment:
      - SPRING_PROFILES_ACTIVE=prod
      - SERVER_PORT=8090
      - EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=http://eureka:8761/eureka/
    ports:
      - "8090:8090"
    depends_on:
      - eureka

volumes:
  postgres-data:
```

### 5.2 部署命令

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 查看状态
docker-compose ps

# 停止所有服务
docker-compose down

# 升级服务
docker-compose up -d --build user-service

# 回滚
docker-compose rollback
```

---

## 6. Kubernetes 部署

### 6.1 Deployment 配置

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway
  labels:
    app: gateway
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gateway
  template:
    metadata:
      labels:
        app: gateway
    spec:
      containers:
        - name: gateway
          image: springcloud-demo/gateway:latest
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: EUREKA_CLIENT_SERVICEURL_DEFAULTZONE
              value: "http://eureka:8761/eureka/"
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /actuator/health
              port: 8080
            initialDelaySeconds: 60
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /actuator/health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 5
```

### 6.2 Service 配置

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway
spec:
  selector:
    app: gateway
  ports:
    - port: 80
      targetPort: 8080
  type: LoadBalancer
```

### 6.3 滚动更新

```bash
# 更新镜像
kubectl set image deployment/gateway gateway=springcloud-demo/gateway:v1.1.0

# 查看更新状态
kubectl rollout status deployment/gateway

# 回滚
kubectl rollout undo deployment/gateway
```

---

## 7. 监控与告警

### 7.1 健康检查

```bash
# 检查所有服务健康状态
for port in 8761 8080 8081 8082 8090; do
    if curl -sf http://localhost:${port}/actuator/health > /dev/null 2>&1; then
        echo "✓ 服务端口 ${port} 正常"
    else
        echo "✗ 服务端口 ${port} 异常"
    fi
done
```

### 7.2 告警配置

| 告警项 | 条件 | 动作 |
|--------|------|------|
| 服务宕机 | health=down | 立即通知 |
| 错误率 | >5% 持续5分钟 | 通知 |
| 响应时间 | P99>3s 持续5分钟 | 通知 |
| CPU | >80% 持续10分钟 | 通知 |
| 内存 | >85% 持续10分钟 | 通知 |

---

## 8. 快速命令参考

```bash
# VM 部署
/opt/springcloud-demo/scripts/deploy.sh

# VM 升级
/opt/springcloud-demo/scripts/upgrade.sh v1.1.0

# VM 回滚
/opt/springcloud-demo/scripts/rollback.sh v1.0.0

# VM 卸载
/opt/springcloud-demo/scripts/uninstall.sh

# Docker 部署
docker-compose up -d

# Docker 停止
docker-compose down

# K8s 部署
kubectl apply -f k8s/

# K8s 查看状态
kubectl get pods -l app=springcloud

# K8s 查看日志
kubectl logs -f deployment/gateway
```

---

最后更新: 2026-03-17
