# Spring Cloud Demo 整体架构设计方案

## 1. 当前架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              整体架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         Nacos Server (8848)  ← 可选部署            │   │
│   │   ┌───────────────────────────────────────────────────────────────┐  │   │
│   │   │  配置中心 (Nacos Config)                                     │  │   │
│   │   │  ├── user-service-dev.yml                                    │  │   │
│   │   │  ├── gateway-dev.yml                                         │  │   │
│   │   │  └── shared-config.yml                                       │  │   │
│   │   └───────────────────────────────────────────────────────────────┘  │   │
│   │   ┌───────────────────────────────────────────────────────────────┐  │   │
│   │   │  服务注册发现 (Nacos Discovery)                              │  │   │
│   │   │  启用方式: NACOS_ENABLED=true                                │  │   │
│   │   └───────────────────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                        │
│                                      │ 配置获取 / 服务注册 (可选)              │
│                                      ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                          API Gateway (8080)                         │   │
│   │                   路由 + 鉴权 + 限流 + 日志                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│            │                        │                        │                │
│            │                        │                        │                │
│   ┌────────┴────────┐     ┌────────┴────────┐     ┌───────┴────────┐    │
│   │  User Service    │     │ Config Service  │     │  Ops Service   │    │
│   │    (8081)       │     │    (8082)      │     │    (8083)     │    │
│   └──────────────────┘     └──────────────────┘     └────────────────┘    │
│            │                        │                        │                │
│            └────────────────────────┼────────────────────────┘                │
│                                     │                                         │
│                                     ▼                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      PostgreSQL (8432)                              │   │
│   │   ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐  │   │
│   │   │  business_db  │  │nacos_config  │  │    现有表             │  │   │
│   │   │  (业务数据)   │  │(Nacos元数据) │  │  sys_config等        │  │   │
│   │   └───────────────┘  └───────────────┘  └───────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| **Spring Boot** | 3.5.0 | Java 框架 |
| **Spring Cloud** | 2025.0.0 | 微服务框架 |
| **Nacos** | 2.3.2 | 配置中心 + 服务注册发现 (可选) |
| **PostgreSQL** | 11.15 | 数据库 |
| **Gateway** | - | API 网关 |
| **JWT** | 0.12.3 | 身份认证 |
| **国密算法** | - | SM2/SM3/SM4 |

> **注意**: Nacos 当前为可选组件，本地模式默认禁用。通过设置 `NACOS_ENABLED=true` 启用。

---

## 3. 服务说明

### 3.1 服务列表

| 服务 | 端口 | 说明 | 主要功能 |
|------|------|------|----------|
| **Gateway** | 8080 | API 网关 | 路由、鉴权、限流 |
| **User Service** | 8081 | 用户服务 | 用户管理、RBAC、OIDC |
| **Config Service** | 8082 | 配置服务 | 现有配置管理 API、国密 |
| **Ops Service** | 8083 | 运维服务 | 告警、监控 |
| **Nacos** | 8848 | 配置中心+注册中心 | 配置管理、服务注册 (可选) |
| **PostgreSQL** | 8432 | 数据库 | 业务数据 + Nacos 元数据 |

### 3.2 运行环境

```
本地模式 (当前):
├── Gateway (8080)        - Maven 启动
├── User Service (8081)   - Maven 启动
├── Config Service (8082)  - Maven 启动
└── PostgreSQL (8432)    - 阿里云服务器

Nacos 模式 (可选):
└── Nacos (8848)        - Docker 启动 (可选)
```

---

## 4. 快速启用 Nacos

### 4.1 Docker 启动

```bash
docker run -d --name nacos -p 8848:8848 -e MODE=standalone nacos/nacos-server:v2.3.2
```

### 4.2 启用服务注册

```bash
# 设置环境变量
export NACOS_ENABLED=true
export NACOS_HOST=localhost
export NACOS_PORT=8848
export NACOS_USERNAME=nacos
export NACOS_PASSWORD=nacos

# 重启服务
```

### 4.3 Nacos 控制台配置

访问 http://localhost:8848/nacos

- 用户名: nacos
- 密码: nacos

创建配置:
- Data ID: `shared-config.yml`
- Group: `SHARED_GROUP`
- 内容: 共享配置 YAML

---

## 5. 配置管理

### 5.1 本地配置 (当前模式)

各服务在 `application.yml` 中配置:

```yaml
spring:
  cloud:
    nacos:
      # 禁用 Nacos (本地模式)
      discovery:
        enabled: ${NACOS_ENABLED:false}
```

### 5.2 Nacos 配置 (启用后)

启用 Nacos 后，配置从 Nacos 中心获取:

```yaml
spring:
  cloud:
    nacos:
      server-addr: ${NACOS_HOST:localhost}:${NACOS_PORT:8848}
      username: ${NACOS_USERNAME:nacos}
      password: ${NACOS_PASSWORD:nacos}
      discovery:
        enabled: ${NACOS_ENABLED:true}
      config:
        enabled: ${NACOS_ENABLED:true}
        file-extension: yml
        refresh-enabled: true
```

---

## 6. 现有能力保留

### 6.1 Config Service 功能

| 功能 | 说明 | 状态 |
|------|------|------|
| REST API | /api/config/* 配置管理接口 | ✅ 保留 |
| 数据库存储 | sys_config, openclaw_config 表 | ✅ 保留 |
| 国密加密 | GmCryptUtil 工具 | ✅ 保留 |
| 配置历史 | config_history 表 | ✅ 保留 |

---

## 7. 与旧架构对比

### 7.1 组件对比

| 组件 | 旧架构 | 新架构 |
|------|--------|--------|
| 配置中心 | 本地配置 | Nacos (可选) + 本地 |
| 注册中心 | Eureka | Nacos (可选) + 静态配置 |
| Spring Boot | 3.2.0 | 3.5.0 |
| Spring Cloud | 2023.0.0 | 2025.0.0 |

### 7.2 优势

| 优势 | 说明 |
|------|------|
| **灵活性** | 可选启用 Nacos，本地模式开箱即用 |
| **简化部署** | 无需强制部署 Nacos |
| **平滑迁移** | 本地 ↔ Nacos 模式一键切换 |
| **保持兼容** | 现有功能完全保留 |

---

## 8. 部署模式

### 8.1 本地开发模式 (默认)

```
无需 Nacos，各服务独立运行
- 启动快
- 适合本地开发
- 配置在 application.yml
```

### 8.2 Nacos 模式 (可选)

```
启用 Nacos 后:
- 配置集中管理
- 服务自动注册发现
- 动态配置刷新
```

切换方式:
```bash
# 启用 Nacos
export NACOS_ENABLED=true

# 或在 application.yml 中设置
spring.cloud.nacos.discovery.enabled: true
```

---

## 9. 版本升级记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-18 | 1.0.0 | 初始版本 |
| 2026-03-18 | 2.0.0 | 升级 Spring Boot 3.5.0 + Spring Cloud 2025.0.0 |
| 2026-03-18 | 2.1.0 | 集成 Nacos (可选)，移除 Eureka |

---

## 10. 文档列表

```
docs/
├── ARCHITECTURE.md           # 架构设计 (本文档)
├── NACOS_INTEGRATION.md     # Nacos 集成方案
├── CONFIG_SERVER_JDBC.md    # Spring Cloud Config 数据库方案
├── CONFIG_CENTER_DESIGN.md  # 配置中心设计
├── CONFIG_CENTER_IMPL.md    # 配置中心实施
├── PERMISSION.md            # 权限设计
├── SECURITY.md              # 安全设计
├── nacos/
│   ├── DETAILED_INTRO.md   # Nacos 详细介绍
│   ├── EXTENSION.md        # Nacos 扩展能力
│   ├── OPTIMIZATION.md     # Nacos 优化方案
│   ├── CONFIG_LIST.md      # Nacos 配置清单
│   ├── QUICK_START.md      # 快速启动
│   ├── STARTUP_WINDOWS.md # Windows 启动指南
│   └── bootstrap-template.yml
├── user-service-db.md       # 用户服务数据表设计
├── config-service-db.md     # 配置服务数据表设计
└── ops-service-db.md       # 运维服务数据表设计
```

---

## 11. 后续规划

- [ ] 部署 Nacos 服务器
- [ ] 配置迁移到 Nacos
- [ ] 启用 Nacos Discovery
- [ ] 配置动态刷新测试
- [ ] 生产环境部署
