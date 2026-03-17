# Spring Cloud Demo

基于 Spring Cloud 的微服务 Demo 项目，包含用户认证、权限管理等核心功能。

## 项目文档

| 文档 | 说明 |
|------|------|
| [DESIGN.md](./DESIGN.md) | 系统设计文档 |
| [DEPLOY.md](./DEPLOY.md) | 部署说明 |
| [API.md](./API.md) | API 接口文档 |
| [AGENT.md](./AGENT.md) | 智能体使用指南 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | Spring Boot 3.2.0 |
| 网关 | Spring Cloud Gateway 4.1.0 |
| 注册中心 | Spring Cloud Eureka |
| 配置中心 | Spring Cloud Config |
| 安全 | Spring Security + JWT/OIDC |
| 数据库 | PostgreSQL |
| 国密算法 | BouncyCastle (SM2/SM3/SM4) |

## 模块划分

### 1. user-service (8081) - 用户服务 / 认证中心

**职责：**
- 用户管理（CRUD）
- 用户认证（登录/注册）
- OIDC/OAuth 2.0 授权服务器
- RBAC 权限管理
- 机机账户（AKSK）管理

**核心功能：**
- JWT Token 签发
- Access Token / Refresh Token
- OIDC 发现文档
- JWKS 公钥服务
- 客户端注册

### 2. gateway (8080) - API 网关

**职责：**
- 统一请求入口
- OIDC Token 验证
- 路由转发
- 请求鉴权

**核心功能：**
- JWT 验证过滤器
- OIDC JWKS 集成
- 用户信息传递
- 统一鉴权入口

### 3. config-service (8082) - 配置服务

**职责：**
- Spring Cloud Config Server
- OpenClaw 配置管理
- 密钥管理
- 国密算法支持

**核心功能：**
- 分布式配置中心
- 配置加密存储
- 软件根密钥/硬件根密钥
- SM2/SM3/SM4 国密算法

## 快速开始

### 本地开发

```bash
# 1. 克隆项目
git clone https://github.com/ANewName-1024/spring-cloud-demo.git
cd spring-cloud-demo

# 2. 配置环境变量
# 参考 .env.example

# 3. 启动服务
# 顺序: user-service → gateway → config-service
```

### 服务端口

| 服务 | 端口 |
|------|------|
| Gateway | 8080 |
| User Service | 8081 |
| Config Service | 8082 |

## 核心功能

### 用户认证
- ✅ 用户名密码登录
- ✅ JWT Token 认证
- ✅ OIDC/OAuth 2.0
- ✅ 机机账户 AKSK 认证
- ✅ AKSK 轮转
- ✅ Refresh Token

### 权限管理
- ✅ RBAC 权限模型
- ✅ 角色管理
- ✅ 权限管理
- ✅ 方法级权限控制

### 安全特性
- ✅ 密码加密存储
- ✅ 密码强度验证
- ✅ 敏感信息环境变量配置
- ✅ 国密算法支持

## 项目结构

```
springcloud-demo/
├── user-service/           # 用户服务 + OIDC 授权服务器
├── gateway/               # API 网关
├── config-service/        # 配置服务 + Spring Cloud Config
├── config-repo/           # 配置文件仓库
├── DESIGN.md             # 设计文档
├── DEPLOY.md             # 部署说明
├── API.md                # 接口文档
└── AGENT.md             # 智能体使用指南
```

## 环境要求

- JDK 21+
- Maven 3.9+
- PostgreSQL

## 相关文档

详细文档请查看：
- [系统设计](./DESIGN.md)
- [部署说明](./DEPLOY.md)
- [接口文档](./API.md)
- [智能体指南](./AGENT.md)

## License

MIT
