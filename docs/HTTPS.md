# HTTPS 证书管理方案

## 概述

本文档描述 Spring Cloud Demo 项目的 HTTPS 证书配置和自动轮转机制。

## 证书架构

```
┌─────────────────────────────────────────────────────────────┐
│                      配置中心 (config-service)                │
│                  统一管理证书配置和策略                        │
└─────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Gateway       │  │  User Service   │  │ Config Service │
│   (8080/8443)  │  │   (8081/8443)   │  │  (8082/8443)   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## 证书配置

### 1. 环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SSL_ENABLED` | 是否启用 HTTPS | false |
| `SSL_KEYSTORE` | 密钥库路径 | classpath:cert/keystore.p12 |
| `SSL_KEYSTORE_PASSWORD` | 密钥库密码 | changeit |
| `SSL_KEYSTORE_TYPE` | 密钥库类型 | PKCS12 |
| `SSL_KEY_ALIAS` | 密钥别名 | server |

### 2. 启动参数示例

```bash
# 启用 HTTPS
java -jar user-service.jar \
  --server.ssl.enabled=true \
  --server.ssl.key-store=/path/to/keystore.p12 \
  --server.ssl.key-store-password=changeit \
  --server.ssl.key-store-type=PKCS12 \
  --server.ssl.key-alias=server
```

## 证书轮转机制

### 1. 轮转流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  检查证书    │ ──▶ │  备份旧证书  │ ──▶ │  生成新证书  │
│  (每天/每周) │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                                               │
         ┌────────────────────┼────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  通知各服务    │  │  更新配置中心  │
│  热加载证书    │  │  证书版本     │
└─────────────────┘  └─────────────────┘
```

### 2. 轮转策略

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `cert.rotation.enabled` | 是否启用自动轮转 | true |
| `cert.rotation.interval-days` | 轮转间隔天数 | 90 |
| `cert.rotation.threshold-days` | 提前提醒天数 | 30 |

### 3. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/ops/cert/info` | 获取证书信息 |
| GET | `/ops/cert/check` | 检查证书是否即将过期 |
| POST | `/ops/cert/rotate` | 手动触发轮转 |

## 证书生成

### 1. 使用 OpenSSL 生成自签名证书

```bash
# 生成私钥
openssl genrsa -out server.key 2048

# 生成自签名证书 (10年有效期)
openssl req -new -x509 \
  -key server.key \
  -out server.crt \
  -days 3650 \
  -subj "/CN=8.137.116.121"

# 转换为 PKCS12 格式
openssl pkcs12 -export \
  -in server.crt \
  -inkey server.key \
  -out keystore.p12 \
  -name server \
  -password pass:changeit
```

### 2. 使用 Java KeyTool 生成

```bash
# 生成密钥对和自签名证书
keytool -genkeypair \
  -alias server \
  -keyalg RSA \
  -keysize 2048 \
  -validity 3650 \
  -keystore keystore.p12 \
  -storetype PKCS12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=8.137.116.121, OU=Dev, O=Example, L=Beijing, ST=Beijing, C=CN"
```

## 配置中心证书管理

### 1. 证书存储

证书存储在配置中心的 `cert` 目录下：

```
config-service/
└── src/main/resources/
    └── cert/
        ├── keystore.p12      # 主证书
        └── keystore.p12.old  # 备份证书
```

### 2. 证书版本管理

每次轮转后，新证书版本会存储到配置中心，各服务通过配置刷新获取新证书。

## 安全注意事项

1. **密钥库密码**：通过环境变量传入，不要硬编码
2. **备份策略**：轮转前自动备份旧证书
3. **监控告警**：证书到期前30天自动告警
4. **审计日志**：记录所有证书操作

## 生产环境建议

1. 使用正式 CA 签发的证书
2. 启用 HSTS (HTTP Strict Transport Security)
3. 配置 TLS 1.3
4. 使用硬件安全模块 (HSM) 存储私钥
5. 配置证书透明度 (Certificate Transparency)

---

最后更新: 2026-03-17
