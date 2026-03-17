# 配置中心设计方案

## 1. 当前配置现状

```
各服务配置现状：
├── config-service      # 自身配置 hardcode，配置管理能力未使用
├── user-service        # 配置文件 + config-repo (未真正使用)
├── gateway             # 配置文件 hardcode
├── ops-service         # 配置文件 hardcode
└── eureka-server      # 配置文件 hardcode

config-repo (Spring Cloud Config 仓库)：
└── user-service.yml   # 仅一个文件，未真正被依赖
```

**问题**：
- config-service 配置管理能力未使用
- 各服务配置分散，难以统一管理
- 配置变更需要重启服务
- 敏感信息散落各处

---

## 2. 配置分类设计

### 2.1 中心化配置 (config-service 管理)

| 配置类型 | 说明 | 示例 | 管理方式 |
|----------|------|------|----------|
| **共享配置** | 所有服务共用 | 数据库连接、Eureka地址、JWT密钥 | config-service |
| **业务配置** | 各服务业务参数 | 限流阈值、重试次数、业务开关 | config-service |
| **敏感配置** | 需要加密的配置 | 密码、密钥、Token | config-service + 加密 |

### 2.2 本地配置 (各模块自行管理)

| 配置类型 | 说明 | 示例 | 原因 |
|----------|------|------|------|
| **启动必需** | 启动时必须知道的值 | server.port、应用名 | 找不到配置中心时也能启动 |
| **环境强相关** | 极度环境依赖 | 本地调试配置 | 不适合集中管理 |
| **高频变更** | 变更非常频繁 | 调试日志级别 | 避免频繁调用配置中心 |

---

## 3. 配置中心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         配置中心                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    config-service                           ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        ││
│  │  │ 配置 REST   │  │  配置管理   │  │  动态刷新  │        ││
│  │  │   API       │  │   Web UI   │  │  Webhook   │        ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘        ││
│  │         │                  │                  │             ││
│  │  ┌──────┴──────────────────┴──────────────────┴──────────┐ ││
│  │  │              配置仓储 (PostgreSQL)                     │ ││
│  │  │  sys_config / openclaw_config / config_history        │ ││
│  │  └───────────────────────────────────────────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
           ▲                    ▲                    ▲
           │                    │                    │
    ┌──────┴──────┐      ┌─────┴─────┐       ┌─────┴─────┐
    │   Gateway   │      │   User    │       │   Ops     │
    │   Service   │      │  Service  │       │  Service  │
    └─────────────┘      └───────────┘       └───────────┘
```

---

## 4. 动态配置实现

### 4.1 技术方案

**方案 A: Spring Cloud Config + Bus (推荐)**
- 使用 Spring Cloud Config Server
- 使用 Spring Cloud Bus (RabbitMQ/Kafka) 广播刷新
- 成熟稳定，社区支持好

**方案 B: Spring Boot Actuator 手动刷新**
- 各服务暴露 `/actuator/refresh` 端点
- 调用配置中心 API 后手动触发刷新
- 简单，适合小型项目

**方案 C: 使用 config-service 自身能力**
- config-service 提供配置读取 API
- 各服务启动时拉取 + 定时轮询/长轮询更新
- 实现简单，与现有架构兼容

### 4.2 本项目采用方案 C

**原因**：
1. 不引入额外中间件（RabbitMQ/Kafka）
2. 与现有 config-service 整合
3. 实现简单，效果明显

---

## 5. 配置接口设计

### 5.1 config-service 提供配置 API

```
GET /api/config/{service-name}           # 获取服务配置
GET /api/config/{service-name}/{key}     # 获取单个配置
POST /api/config/{service-name}          # 设置配置 (需认证)
PUT  /api/config/{service-name}/{key}    # 更新配置 (需认证)
DELETE /api/config/{service-name}/{key}  # 删除配置 (需认证)
POST /api/config/notify                  # 通知配置变更 (Webhook)
```

### 5.2 配置 JSON 格式

```json
{
  "service": "user-service",
  "version": "20260318",
  "config": {
    "spring.datasource.url": "jdbc:postgresql://...",
    "jwt.secret": "xxx",
    "custom.feature.enabled": true
  },
  "lastModified": "2026-03-18T07:00:00Z"
}
```

---

## 6. 各服务配置清单

### 6.1 user-service

| 配置项 | 类别 | 管理方式 | 原因 |
|--------|------|----------|------|
| server.port | 本地 | application.yml | 启动必需 |
| spring.datasource.* | 中心 | config-service | 共享 |
| jwt.secret | 中心 | config-service | 敏感 |
| jwt.expiration | 中心 | config-service | 业务 |
| eureka.client.* | 中心 | config-service | 共享 |

### 6.2 gateway

| 配置项 | 类别 | 管理方式 | 原因 |
|--------|------|----------|------|
| server.port | 本地 | application.yml | 启动必需 |
| eureka.client.* | 中心 | config-service | 共享 |
| jwt.secret | 中心 | config-service | 敏感 |
| gateway.routes | 本地 | application.yml | 路由少变 |

### 6.3 config-service

| 配置项 | 类别 | 管理方式 | 原因 |
|--------|------|----------|------|
| server.port | 本地 | application.yml | 启动必需 |
| spring.datasource.* | 本地 | application.yml | 自身配置 |
| config.jwt.* | 本地 | application.yml | 自身认证 |

### 6.4 ops-service

| 配置项 | 类别 | 管理方式 | 原因 |
|--------|------|----------|------|
| server.port | 本地 | application.yml | 启动必需 |
| eureka.client.* | 中心 | config-service | 共享 |
| ops.alert.thresholds.* | 中心 | config-service | 业务 |

---

## 7. 实施计划

### Phase 1: config-service 配置 API
- [ ] 完善配置 CRUD API
- [ ] 添加配置版本管理
- [ ] 添加配置变更通知（WebSocket/长轮询）

### Phase 2: 客户端 SDK
- [ ] 开发 config-client SDK
- [ ] 实现启动时拉取配置
- [ ] 实现动态配置监听

### Phase 3: 迁移配置
- [ ] 迁移共享配置到 config-service
- [ ] 各服务保留启动必需配置
- [ ] 测试动态刷新

### Phase 4: 管理界面
- [ ] 配置管理 Web UI
- [ ] 配置对比/回滚
- [ ] 审计日志

---

## 8. 配置示例

### 8.1 中心化配置 (config-service)

```json
{
  "service": "shared",
  "config": {
    "eureka.host": "8.137.116.121",
    "eureka.port": "9000",
    "eureka.username": "admin",
    "eureka.password": "${EUREKA_PASSWORD}",
    "db.host": "8.137.116.121",
    "db.port": "8432",
    "db.name": "business_db",
    "db.username": "business",
    "db.password": "${DB_PASSWORD}",
    "jwt.secret": "${JWT_SECRET}",
    "jwt.expiration": "1800000"
  }
}
```

### 8.2 本地配置 (application.yml)

```yaml
# user-service/src/main/resources/application.yml
server:
  port: 8081

spring:
  application:
    name: user-service
  config:
    import: optional:http://localhost:8082/api/config/user-service

# 启动必需配置 (找不到配置中心时使用)
  datasource:
    url: jdbc:postgresql://${DB_HOST:localhost}:${DB_PORT:5432}/${DB_NAME:business_db}
    username: ${DB_USERNAME:business}
    password: ${DB_PASSWORD:}

# 本地开发配置
---
spring:
  config:
    activate:
      on-profile: local
  datasource:
    url: jdbc:postgresql://localhost:5432/business_db
    password: devpassword
```

---

## 9. 安全考虑

1. **配置加密存储**：敏感配置使用 AES-256-GCM 加密
2. **访问控制**：配置 API 需要认证
3. **审计日志**：记录所有配置变更
4. **配置版本**：支持配置回滚
5. **差异化权限**：普通用户只能查看，管理员可修改
