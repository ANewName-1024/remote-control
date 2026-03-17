# Spring Cloud Demo

基于 Spring Cloud 的微服务 Demo 项目，包含用户认证、权限管理、运维监控等核心功能。

## 项目概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户请求                                 │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Gateway (8080)                                │
│  - JWT/OIDC 认证                                                │
│  - 请求路由                                                      │
│  - 限流                                                          │
│  - 日志追踪                                                      │
└────────────────────────────┬────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ user-service   │ │ config-service  │ │  ops-service    │
│    (8081)     │ │    (8082)      │ │    (8090)       │
│               │ │                │ │                 │
│ OIDC 授权     │ │ Spring Cloud   │ │  运维监控        │
│ 用户管理      │ │ Config         │ │  告警管理        │
│ RBAC 权限     │ │ XXL-JOB 调度   │ │  日志聚合        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
           │                 │                 │
           └─────────────────┼─────────────────┘
                             ▼
                  ┌─────────────────┐
                  │  Eureka (8761)  │
                  │  服务注册发现    │
                  └─────────────────┘
```

## 模块划分

| 模块 | 端口 | 职责 |
|------|------|------|
| eureka-server | 8761 | 服务注册与发现 |
| gateway | 8080 | API 网关、认证鉴权 |
| user-service | 8081 | 用户服务、OIDC 授权 |
| config-service | 8082 | 配置管理服务 (H2 内存数据库) |
| ops-service | 8090 | 运维监控、告警管理 |
| common | - | 公共模块 |

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 运行时 | Java | 21 |
| 框架 | Spring Boot | 3.2.0 |
| 微服务 | Spring Cloud | 2023.0.0 |
| 网关 | Spring Cloud Gateway | 4.1.0 |
| 注册中心 | Netflix Eureka | - |
| 配置管理 | 自定义 REST API + H2 | - |
| 安全 | Spring Security + JWT/OIDC | 6.2.0 |
| 数据库 | H2 (开发) / PostgreSQL (生产) | - |

## 核心功能

### 用户认证与权限
- ✅ 用户名密码登录/注册
- ✅ JWT Token 签发与验证
- ✅ OIDC/OAuth 2.0 授权服务器
- ✅ RBAC 权限模型
- ✅ 机机账户 (AKSK) 认证
- ✅ Refresh Token 刷新
- ✅ 密码强度验证 + 弱密码检测
- ✅ 敏感字段国密加密存储

### API 网关
- ✅ JWT/OIDC Token 验证
- ✅ 请求路由转发 (LoadBalancer)
- ✅ 限流 (100 req/min)
- ✅ 请求日志 + Trace ID 追踪
- ✅ 动态服务发现
- ✅ CORS 配置

### 配置中心
- ✅ 配置管理 REST API
- ✅ H2 内存数据库存储
- ✅ 配置版本历史记录

### 运维监控
- ✅ 统一异常处理
- ✅ 日志规范设计 (ELK)
- ✅ 告警管理 (Ops Service)
- ✅ 敏感信息保护方案

## 快速开始

### 环境要求

- JDK 21+
- Maven 3.9+
- PostgreSQL

### 启动服务

```bash
# 1. 克隆项目
git clone https://github.com/ANewName-1024/spring-cloud-demo.git
cd spring-cloud-demo

# 2. 编译项目
mvn clean package -DskipTests

# 3. 启动服务 (按顺序)
java -jar eureka-server/target/eureka-server-1.0.0.jar
java -jar user-service/target/user-service-1.0.0.jar
java -jar config-service/target/config-service-1.0.0.jar
java -jar gateway/target/gateway-1.0.0.jar
java -jar ops-service/target/ops-service-1.0.0.jar

# 或使用 Docker Compose
docker-compose up -d
```

### 服务端口

| 服务 | 端口 | 访问地址 |
|------|------|----------|
| Gateway | 8080 | http://localhost:8080 |
| User Service | 8081 | http://localhost:8081 |
| Config Service | 8082 | http://localhost:8082 |
| Ops Service | 8090 | http://localhost:8090 |
| Eureka | 8761 | http://localhost:8761 |

## 项目结构

```
springcloud-demo/
├── eureka-server/          # 服务注册中心 (8761)
├── gateway/               # API 网关 (8080)
├── user-service/          # 用户服务 + OIDC (8081)
├── config-service/        # 配置中心 + XXL-JOB (8082)
├── ops-service/          # 运维服务 (8090)
├── common/               # 公共模块
├── elk/                  # ELK 配置
├── scripts/              # 部署脚本
├── docs/                 # 详细文档
│   ├── DESIGN.md         # 系统设计
│   ├── API.md           # 接口文档
│   ├── DEPLOY.md        # 部署指南
│   ├── OPS.md           # 运维设计
│   ├── LOGGING.md       # 日志规范
│   ├── EXCEPTION.md     # 异常处理
│   ├── ENCRYPTION.md    # 加密方案
│   ├── SECURITY.md      # 安全方案
│   ├── TESTING.md       # 测试规范
│   ├── AUTO_DEPLOY.md   # 自动化部署
│   └── PERMISSION.md    # 权限管理
└── README.md
```

## 文档索引

| 文档 | 说明 |
|------|------|
| [README.md](./README.md) | 项目概览 |
| [DESIGN.md](./DESIGN.md) | 系统架构设计 |
| [API.md](./API.md) | API 接口文档 |
| [DEPLOY.md](./DEPLOY.md) | 部署指南 |
| [OPS.md](./OPS.md) | 运维服务设计 |
| [LOGGING.md](./docs/LOGGING.md) | 日志设计规范 |
| [EXCEPTION.md](./docs/EXCEPTION.md) | 异常处理设计 |
| [ENCRYPTION.md](./docs/ENCRYPTION.md) | 敏感字段加密方案 |
| [SECURITY.md](./docs/SECURITY.md) | 敏感信息保护方案 |
| [TESTING.md](./docs/TESTING.md) | 测试规范 |
| [AUTO_DEPLOY.md](./docs/AUTO_DEPLOY.md) | 自动化部署 |
| [PERMISSION.md](./docs/PERMISSION.md) | 权限管理 |
| [AGENT.md](./AGENT.md) | 智能体使用指南 |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | 开发规范 |
| [BRANCH_STRATEGY.md](./BRANCH_STRATEGY.md) | 分支策略 |

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| DB_HOST | 数据库地址 | 8.137.116.121 |
| DB_PORT | 数据库端口 | 5432 |
| DB_NAME | 数据库名称 | business_db |
| DB_USERNAME | 数据库用户名 | business |
| DB_PASSWORD | 数据库密码 | - |
| EUREKA_HOST | Eureka 地址 | 8.137.116.121 |
| EUREKA_PORT | Eureka 端口 | 8761 |
| JWT_SECRET | JWT 密钥 | - |
| OIDC_ISSUER | OIDC 签发者 | http://localhost:8081 |
| ENCRYPTION_KEY | 加密密钥 | - |

## License

MIT

---

最后更新: 2026-03-18
