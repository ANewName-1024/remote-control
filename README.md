# README - Spring Cloud Demo

## 项目简介

Spring Cloud 微服务架构演示项目，包含配置中心、服务注册、API网关、用户服务等功能。

## 技术栈

| 组件 | 版本 |
|------|------|
| Spring Boot | 3.5.0 |
| Spring Cloud | 2025.0.0 |
| Spring Cloud Alibaba | 2023.0.1.2 |
| Nacos | 2.3.2 (可选) |
| PostgreSQL | 11.15 |
| Java | 21 |

## 项目结构

```
springcloud-demo/
├── common/              # 公共模块
├── gateway/            # API 网关 (8080)
├── user-service/        # 用户服务 (8081)
├── config-service/       # 配置服务 (8082)
├── ops-service/         # 运维服务 (8083)
├── eureka-server/       # Eureka 服务 (已废弃)
└── docs/               # 设计文档
```

## 快速开始

### 本地模式 (无需 Nacos)

```bash
# 编译项目
mvn clean compile

# 启动服务 (按顺序)
mvn -f config-service/pom.xml spring-boot:run
mvn -f user-service/pom.xml spring-boot:run  
mvn -f gateway/pom.xml spring-boot:run
```

服务端口:
- Gateway: http://localhost:8080
- User Service: http://localhost:8081
- Config Service: http://localhost:8082
- Ops Service: http://localhost:8083

### Nacos 模式 (可选)

```bash
# 启动 Nacos
docker run -d --name nacos -p 8848:8848 -e MODE=standalone nacos/nacos-server:v2.3.2

# 启用 Nacos
export NACOS_ENABLED=true

# 重启服务
```

## 功能特性

- [x] API 网关 (路由、鉴权)
- [x] 用户服务 (RBAC、OIDC)
- [x] 配置服务 (REST API、国密加密)
- [x] 运维服务 (告警、监控)
- [x] Nacos 集成 (可选)
- [ ] 配置动态刷新

## 文档

详见 `docs/` 目录:

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - 架构设计
- [NACOS_INTEGRATION.md](docs/NACOS_INTEGRATION.md) - Nacos 集成
- [nacos/](docs/nacos/) - Nacos 详细文档

## 升级记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-03-18 | 2.1.0 | 集成 Nacos，移除 Eureka |
| 2026-03-18 | 2.0.0 | 升级 Spring Boot 3.5.0 |
| 2026-03-17 | 1.0.0 | 初始版本 |

## License

MIT
