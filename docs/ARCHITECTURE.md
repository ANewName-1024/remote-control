# Spring Cloud Demo 整体架构设计方案

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              整体架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         Nacos Server (8848)                          │   │
│   │   ┌───────────────────────────────────────────────────────────────┐  │   │
│   │   │  配置中心 (Nacos Config)                                     │  │   │
│   │   │  ├── user-service-dev.yml                                    │  │   │
│   │   │  ├── gateway-dev.yml                                        │  │   │
│   │   │  ├── ops-service-dev.yml                                    │  │   │
│   │   │  └── shared-config.yml (共享配置)                           │  │   │
│   │   └───────────────────────────────────────────────────────────────┘  │   │
│   │   ┌───────────────────────────────────────────────────────────────┐  │   │
│   │   │  服务注册发现 (Nacos Discovery)                              │  │   │
│   │   │  ├── Gateway                                                 │  │   │
│   │   │  ├── User-Service                                           │  │   │
│   │   │  ├── Config-Service                                         │  │   │
│   │   │  └── Ops-Service                                            │  │   │
│   │   └───────────────────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                        │
│                                      │ 配置获取 / 服务注册                     │
│                                      ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                           API Gateway (8080)                         │   │
│   │                    路由 + 鉴权 + 限流 + 日志                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│            │                        │                        │                │
│            │                        │                        │                │
│   ┌────────┴────────┐     ┌────────┴────────┐     ┌───────┴────────┐    │
│   │  User Service  │     │ Config Service  │     │  Ops Service   │    │
│   │    (8081)     │     │    (8082)      │     │    (8083)     │    │
│   └────────────────┘     └─────────────────┘     └────────────────┘    │
│            │                        │                        │                │
│            └────────────────────────┼────────────────────────┘                │
│                                     │                                         │
│                                     ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    PostgreSQL (8432)                               │   │
│   │   ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐  │   │
│   │   │ business_db   │  │ nacos_config │  │   现有表             │  │   │
│   │   │ (业务数据)    │  │ (Nacos元数据)│  │ sys_config等        │  │   │
│   │   └───────────────┘  └───────────────┘  └───────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Spring Boot | 3.5.0 | Java 框架 |
| Spring Cloud | 2025.0.0 | 微服务框架 |
| Nacos | 2.3.2 | 配置中心 + 服务发现 |
| PostgreSQL | 11.15 | 数据库 |
| Gateway | - | API 网关 |
| JWT | 0.12.3 | 身份认证 |
| 国密算法 | - | SM2/SM3/SM4 |

---

## 3. 服务说明

### 3.1 服务列表

| 服务 | 端口 | 说明 | 主要功能 |
|------|------|------|----------|
| **Gateway** | 8080 | API 网关 | 路由、鉴权、限流 |
| **User Service** | 8081 | 用户服务 | 用户管理、RBAC、OIDC |
| **Config Service** | 8082 | 配置服务 | 现有配置管理 API、国密 |
| **Ops Service** | 8083 | 运维服务 | 告警、监控 |
| **Nacos** | 8848 | 配置中心 | 配置管理、服务注册 |
| **PostgreSQL** | 8432 | 数据库 | 业务数据 + Nacos 元数据 |

### 3.2 服务依赖

```
Gateway
  │
  ├── 依赖 Nacos (服务发现)
  │
  └── 路由到
        ├── User Service
        ├── Config Service
        └── Ops Service

User Service
  │
  ├── 依赖 Nacos (配置 + 注册)
  │
  └── 依赖 PostgreSQL (业务数据)

Config Service
  │
  ├── 依赖 Nacos (可选配置)
  │
  └── 依赖 PostgreSQL (配置存储)

Ops Service
  │
  ├── 依赖 Nacos (配置 + 注册)
  │
  └── 依赖 PostgreSQL (告警数据)
```

---

## 4. 配置管理

### 4.1 Nacos 配置结构

```
Namespace: public (默认)
  │
  ├── Group: DEFAULT_GROUP
  │   ├── user-service-dev.yml
  │   ├── user-service-prod.yml
  │   ├── gateway-dev.yml
  │   ├── gateway-prod.yml
  │   ├── config-service-dev.yml
  │   └── ops-service-dev.yml
  │
  └── Group: SHARED_GROUP
      ├── shared-config.yml    # 共享配置 (数据库、Eureka)
      └── jwt-config.yml       # JWT 配置
```

### 4.2 配置内容

#### shared-config.yml (共享配置)

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST:8.137.116.121}:${DB_PORT:8432}/${DB_NAME:business_db}
    username: ${DB_USERNAME:business}
    password: ${DB_PASSWORD:NewPass2024}
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2

eureka:
  client:
    service-url:
      defaultZone: http://${EUREKA_USER:admin}:${EUREKA_PASSWORD:EurekaNew2024}@${EUREKA_HOST:8.137.116.121}:${EUREKA_PORT:9000}/eureka/
    register-with-eureka: true
    fetch-registry: true
  instance:
    prefer-ip-address: true
```

#### user-service-dev.yml

```yaml
server:
  port: 8081

spring:
  application:
    name: user-service

jwt:
  secret: ${JWT_SECRET:UserServiceJWTSecretKey2024}
  expiration: 1800000

logging:
  level:
    com.example.user: DEBUG
```

### 4.3 各服务 bootstrap.yml

```yaml
spring:
  application:
    name: user-service
  cloud:
    nacos:
      server-addr: ${NACOS_HOST:localhost}:${NACOS_PORT:8848}
      username: ${NACOS_USERNAME:nacos}
      password: ${NACOS_PASSWORD:nacos}
      config:
        namespace: public
        group: DEFAULT_GROUP
        file-extension: yml
        refresh-enabled: true
        shared-configs:
          - data-id: shared-config.yml
            group: SHARED_GROUP
            refresh: true
```

---

## 5. 服务注册发现

### 5.1 Nacos 服务列表

```
注册到 Nacos 的服务:

┌─────────────────┬────────────┬────────────────────────────────┐
│ ServiceName     │ Port      │ Metadata                      │
├─────────────────┼────────────┼────────────────────────────────┤
│ gateway         │ 8080      │ version: 1.0.0                │
│ user-service    │ 8081      │ version: 1.0.0                │
│ config-service  │ 8082      │ version: 1.0.0                │
│ ops-service     │ 8083      │ version: 1.0.0                │
└─────────────────┴────────────┴────────────────────────────────┘
```

### 5.2 Gateway 路由配置

```yaml
spring:
  cloud:
    nacos:
      discovery:
        server-addr: ${NACOS_HOST:localhost}:${NACOS_PORT:8848}
    gateway:
      discovery:
        locator:
          enabled: true  # 启用服务发现路由
          lower-case-service-id: true
      routes:
        - id: user-service
          uri: lb://user-service  # 使用负载均衡
          predicates:
            - Path=/user/**
        - id: config-service
          uri: lb://config-service
          predicates:
            - Path=/config/**
```

---

## 6. 现有能力保留

### 6.1 Config Service 保留功能

| 功能 | 说明 | 状态 |
|------|------|------|
| REST API | /api/config/* 配置管理接口 | ✅ 保留 |
| 数据库存储 | sys_config, openclaw_config 表 | ✅ 保留 |
| 国密加密 | GmCryptUtil 工具 | ✅ 保留 |
| 配置历史 | config_history 表 | ✅ 保留 |

### 6.2 架构整合

```
                    Nacos (配置中心)
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐
    │ Gateway  │    │  User   │    │  Ops    │
    └─────────┘    └─────────┘    └─────────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
                    ┌─────┴─────┐
                    │ Config    │
                    │ Service   │
                    └───────────┘
                          │
                    ┌─────┴─────┐
                    │ PostgreSQL │
                    │ (业务+配置)│
                    └───────────┘
```

---

## 7. 安全设计

### 7.1 认证流程

```
用户请求
    │
    ▼
┌─────────────┐
│  Gateway   │
│  (JWT验证) │
└──────┬──────┘
       │ 验证通过
       ▼
┌─────────────┐
│  业务服务   │
└─────────────┘
```

### 7.2 Nacos 安全

| 安全措施 | 说明 |
|----------|------|
| 认证 | 用户名/密码登录 |
| 权限控制 | Namespace/Group 级别权限 |
| HTTPS | 生产环境启用 HTTPS |
| 加密存储 | 敏感配置 AES 加密 |

---

## 8. 部署方案

### 8.1 开发环境

```
本机运行:
├── Nacos (8848)        - Docker 或嵌入式
├── Gateway (8080)       - Maven 启动
├── User Service (8081)  - Maven 启动
├── Config Service (8082) - Maven 启动
└── PostgreSQL (8432)    - 阿里云服务器
```

### 8.2 生产环境

```
阿里云服务器:
├── Nacos Cluster (8848)    - 3 节点
├── Gateway Cluster (8080)  - 2 节点
├── User Service (8081)     - 2 节点
├── Config Service (8082)   - 2 节点
├── Ops Service (8083)     - 2 节点
└── PostgreSQL (8432)      - 主从复制
```

---

## 9. 实施计划

### Phase 1: 基础搭建 (1-2天)
- [ ] 部署 Nacos Server
- [ ] 配置 Nacos 数据库 (PostgreSQL)
- [ ] 创建 Nacos 配置

### Phase 2: 服务集成 (2-3天)
- [ ] 各服务添加 Nacos 依赖
- [ ] 修改 bootstrap.yml
- [ ] 测试配置获取
- [ ] 测试动态刷新

### Phase 3: 服务注册 (1-2天)
- [ ] 各服务添加 Nacos Discovery
- [ ] Gateway 启用服务发现路由
- [ ] 测试服务调用

### Phase 4: 优化完善 (1-2天)
- [ ] 配置版本管理
- [ ] 权限控制
- [ ] 监控告警
- [ ] 文档完善

---

## 10. 配置文件汇总

### 10.1 Nacos 配置清单

| Data ID | 环境 | 说明 |
|---------|------|------|
| shared-config.yml | 共享 | 数据库、Eureka 配置 |
| jwt-config.yml | 共享 | JWT 密钥配置 |
| gateway-dev.yml | 开发 | Gateway 开发配置 |
| gateway-prod.yml | 生产 | Gateway 生产配置 |
| user-service-dev.yml | 开发 | 用户服务开发配置 |
| user-service-prod.yml | 生产 | 用户服务生产配置 |
| config-service-dev.yml | 开发 | 配置服务开发配置 |
| ops-service-dev.yml | 开发 | 运维服务开发配置 |

### 10.2 环境变量

```bash
# Nacos
export NACOS_HOST=localhost
export NACOS_PORT=8848
export NACOS_USERNAME=nacos
export NACOS_PASSWORD=nacos

# Database
export DB_HOST=8.137.116.121
export DB_PORT=8432
export DB_NAME=business_db
export DB_USERNAME=business
export DB_PASSWORD=NewPass2024
```

---

## 11. 架构优势

| 优势 | 说明 |
|------|------|
| **集中配置** | 所有配置在 Nacos 管理 |
| **动态刷新** | 配置变更无需重启 |
| **服务发现** | 自动注册和发现 |
| **负载均衡** | Gateway 自动负载 |
| **高可用** | 支持集群部署 |
| **可视化** | Nacos 控制台管理 |
