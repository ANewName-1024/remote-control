# AGENT.md - 项目智能体使用指南

## 项目概述

本项目是一个基于 Spring Cloud 的微服务 Demo，专注于用户认证和权限管理。支持 OIDC 协议标准，可作为其他系统的认证授权服务。

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Java | 21 | 运行环境 |
| Spring Boot | 3.2.0 | 基础框架 |
| Spring Cloud | 2023.0.0 | 微服务框架 |
| Spring Cloud Gateway | 4.1.0 | API 网关 |
| Spring Security | 6.2.0 | 安全框架 |
| PostgreSQL | - | 数据库 |
| JWT/jjwt | 0.12.3 | Token 签发 |
| BouncyCastle | 1.70 | 国密算法 |

## 项目结构

```
springcloud-demo/
├── user-service/              # 用户服务 + OIDC 授权服务器
│   ├── src/main/java/.../
│   │   ├── controller/       # REST API 控制器
│   │   │   ├── AuthController.java      # 用户认证
│   │   │   └── oidc/
│   │   │       └── OidcController.java # OIDC 端点
│   │   ├── service/         # 业务逻辑
│   │   │   ├── AuthService.java
│   │   │   └── oidc/
│   │   │       ├── OidcTokenService.java      # Token 签发
│   │   │       └── OidcAuthorizationService.java
│   │   ├── entity/          # 数据实体
│   │   ├── repository/     # JPA 仓库
│   │   ├── security/       # 安全组件
│   │   └── oidc/          # OIDC 实现
│   └── src/main/resources/
│       └── application.yml  # 配置文件
│
├── gateway/                  # API 网关
│   └── src/main/java/.../
│       └── filter/
│           └── OidcAuthenticationFilter.java  # OIDC Token 验证
│
├── config-service/           # 配置服务
│   └── src/main/java/.../
│       ├── security/
│       │   ├── GmCryptUtil.java       # 国密算法
│       │   └── KeyManagementService.java
│       └── service/
│           └── OpenClawConfigService.java
│
├── DESIGN.md                 # 系统设计文档
├── DEPLOY.md                 # 部署说明
├── API.md                    # 接口文档
└── README.md                 # 项目说明
```

## 核心功能

### 1. OIDC/OAuth 2.0 授权服务

**支持的授权流程：**
- Authorization Code + PKCE（前端应用）
- Client Credentials（机机账户）
- Refresh Token（Token 刷新）
- Password（遗留系统）

**OIDC 端点：**
| 端点 | 说明 |
|------|------|
| `GET /.well-known/openid-configuration` | OIDC 发现文档 |
| `GET /oauth/jwks` | JSON Web Key Set |
| `GET /oauth/authorize` | 授权端点 |
| `POST /oauth/token` | Token 端点 |
| `GET /oauth/userinfo` | 用户信息 |

### 2. 用户认证

**认证方式：**
- 用户名密码登录
- AKSK 登录（机机账户）

**Token：**
- Access Token：30 分钟有效期
- Refresh Token：7 天有效期
- 支持 Token 刷新和撤销

### 3. RBAC 权限管理

**实体：**
- User（用户）
- Role（角色）
- Permission（权限）
- OidcClient（OIDC 客户端）

**权限模型：**
```
用户 ─── N:M ─── 角色 ─── N:M ─── 权限
```

### 4. 国密算法支持

- SM2：非对称加密
- SM3：摘要算法
- SM4：对称加密

### 5. Gateway 统一鉴权

- OIDC JWT 验证
- JWKS 公钥获取
- 用户信息传递

## 配置说明

### 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_HOST` | 数据库地址 | 8.137.116.121 |
| `DB_PORT` | 数据库端口 | 8432 |
| `DB_NAME` | 数据库名称 | business_db |
| `DB_USERNAME` | 数据库用户名 | business |
| `DB_PASSWORD` | 数据库密码 | - |
| `EUREKA_HOST` | Eureka 地址 | 8.137.116.121 |
| `EUREKA_PORT` | Eureka 端口 | 9000 |
| `EUREKA_USER` | Eureka 用户名 | admin |
| `EUREKA_PASSWORD` | Eureka 密码 | - |
| `JWT_SECRET` | JWT 密钥 | - |
| `OIDC_ISSUER` | OIDC 签发者 | http://localhost:8081 |

### 端口

| 服务 | 端口 |
|------|------|
| Gateway | 8080 |
| user-service | 8081 |
| config-service | 8082 |
| Eureka | 9000 |
| PostgreSQL | 8432 |

## 使用示例

### 1. 注册 OIDC 客户端

```bash
curl -X POST http://localhost:8081/oauth/client/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "MyApp",
    "redirect_uris": "http://localhost:3000/callback",
    "scope": "openid profile email"
  }'
```

### 2. 获取 Token（客户端凭证模式）

```bash
curl -X POST http://localhost:8081/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=xxx" \
  -d "client_secret=xxx" \
  -d "scope=openid"
```

### 3. 通过 Gateway 访问

```bash
# 使用 Token 访问业务接口
curl http://localhost:8080/user/auth/me \
  -H "Authorization: Bearer <access_token>"
```

## 扩展指南

### 添加新的微服务

1. 创建新模块（如 `order-service`）
2. 添加 `pom.xml` 依赖
3. 配置 `application.yml`
4. 注册到 Eureka
5. 在 Gateway 添加路由

### 添加新的认证方式

1. 在 `OidcAuthorizationService` 添加新流程
2. 在 `OidcController` 添加新端点
3. 更新 OIDC 发现文档

### 添加新的加密算法

1. 在 `GmCryptUtil` 添加算法实现
2. 在 `KeyManagementService` 集成
3. 配置为默认算法

## 安全注意事项

- 敏感信息使用环境变量，不要硬编码
- 生产环境修改默认 JWT Secret
- 定期轮换数据库密码
- 启用 HTTPS
- 配置防火墙规则
- 定期更新依赖版本

## 常见问题

**Q: 如何获取 OIDC 发现文档？**
```bash
curl http://localhost:8081/.well-known/openid-configuration
```

**Q: 如何注册新客户端？**
```bash
curl -X POST http://localhost:8081/oauth/client/register
```

**Q: Gateway 如何验证 Token？**
Gateway 从 user-service 的 `/oauth/jwks` 获取公钥，验证 Token 签名。

## 相关文档

- [系统设计](./DESIGN.md)
- [部署说明](./DEPLOY.md)
- [接口文档](./API.md)
