# AGENT.md - 项目智能体使用指南

## 项目概述

本项目是一个基于 Spring Cloud 的微服务 Demo，专注于用户认证和权限管理。支持 OIDC 协议标准，可作为其他系统的认证授权服务。

## 模块业务划分

### 1. user-service (8081) - 用户服务 / 认证中心

**业务职责：**
- 用户生命周期管理（创建、查询、删除）
- 用户认证（用户名密码登录）
- OIDC/OAuth 2.0 授权服务器
- RBAC 权限管理
- 机机账户（AKSK）管理

**核心功能：**

| 功能 | 说明 |
|------|------|
| 用户管理 | 用户 CRUD |
| 用户注册 | 用户名密码注册 |
| 用户登录 | 返回 JWT Token |
| OIDC 授权 | Authorization Code + PKCE |
| OIDC Token | 签发 Access/ID/Refresh Token |
| 客户端注册 | OAuth 2.0 客户端管理 |
| 角色管理 | 角色 CRUD |
| 权限管理 | 权限 CRUD |
| AKSK 管理 | 机机账户创建/轮转 |
| Refresh Token | Token 刷新/撤销 |

**实体：**
- User（用户）
- Role（角色）
- Permission（权限）
- OidcClient（OIDC 客户端）
- ServiceAccount（机机账户）
- RefreshToken（刷新令牌）

**端点：**
```
/user/auth/*       - 用户认证
/oauth/*          - OIDC 授权
/user/admin/*     - 管理接口
```

---

### 2. gateway (8080) - API 网关

**业务职责：**
- 统一请求入口
- OIDC Token 验证
- 路由转发
- 请求鉴权
- CORS 处理

**核心功能：**

| 功能 | 说明 |
|------|------|
| 路由转发 | 转发到后端微服务 |
| Token 验证 | OIDC JWT 验证 |
| JWKS 集成 | 获取公钥验证签名 |
| 用户信息传递 | X-User-Id/X-User-Name Header |
| 统一鉴权 | 一次认证，处处通行 |
| CORS | 跨域支持 |

**配置：**
```yaml
routes:
  - /user/**, /oauth/** → user-service:8081
  - /config/**, /openclaw/** → config-service:8082
```

**豁免路径：**
```
/user/auth/login
/user/auth/register
/oauth/token
/oauth/jwks
/actuator/**
```

---

### 3. config-service (8082) - 配置服务

**业务职责：**
- Spring Cloud Config Server
- OpenClaw 配置存储
- 密钥管理
- 国密算法支持

**核心功能：**

| 功能 | 说明 |
|------|------|
| 配置中心 | Spring Cloud Config Server |
| Git 配置 | 存储在 Git 仓库 |
| 配置加密 | Jasypt 加密 |
| OpenClaw 配置 | 凭证/密钥存储 |
| 密钥管理 | 软件根/硬件根密钥 |
| 国密算法 | SM2/SM3/SM4 |

**实体：**
- OpenClawConfig（OpenClaw 配置）
- SysConfig（系统配置）

**端点：**
```
/{application}/{profile}  - 获取配置
/openclaw/config/*       - OpenClaw 配置管理
```

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户请求                               │
└────────────────────────────┬────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Gateway (8080)                              │
│  1. OIDC Token 验证                                         │
│  2. 路由转发                                                │
│  3. 用户信息传递                                           │
└────────────────────────────┬────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐        ┌─────────────────────┐
│  user-service      │        │  config-service     │
│     (8081)         │        │     (8082)          │
│                    │        │                     │
│ OIDC 授权服务器   │        │ Spring Cloud Config │
│ 用户管理          │        │ OpenClaw 配置       │
│ RBAC 权限         │        │ 密钥管理            │
└─────────────────────┘        └─────────────────────┘
```

## 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Java | 21 | 运行环境 |
| Spring Boot | 3.2.0 | 基础框架 |
| Spring Cloud | 2023.0.0 | 微服务框架 |
| Spring Cloud Gateway | 4.1.0 | API 网关 |
| Spring Cloud Config | 2023.0.0 | 配置中心 |
| Spring Security | 6.2.0 | 安全框架 |
| PostgreSQL | - | 数据库 |
| JWT/jjwt | 0.12.3 | Token 签发 |
| BouncyCastle | 1.70 | 国密算法 |

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
| `EUREKA_PASSWORD` | Eureka 密码 | - |
| `JWT_SECRET` | JWT 密钥 | - |
| `OIDC_ISSUER` | OIDC 签发者 | http://localhost:8081 |

### 端口

| 服务 | 端口 |
|------|------|
| Gateway | 8080 |
| user-service | 8081 |
| config-service | 8082 |

## 使用示例

### 1. 注册 OIDC 客户端

```bash
curl -X POST http://localhost:8081/oauth/client/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"MyApp","redirect_uris":"http://localhost:3000/callback","scope":"openid profile email"}'
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
curl http://localhost:8080/user/auth/me \
  -H "Authorization: Bearer <access_token>"
```

### 4. 获取配置

```bash
curl http://localhost:8082/user-service/dev
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

## 安全注意事项

- 敏感信息使用环境变量，不要硬编码
- 生产环境修改默认 JWT Secret
- 定期轮换数据库密码
- 启用 HTTPS
- 配置防火墙规则
- 定期更新依赖版本

## 相关文档

- [系统设计](./DESIGN.md)
- [部署说明](./DEPLOY.md)
- [接口文档](./API.md)
