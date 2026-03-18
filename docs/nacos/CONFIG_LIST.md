# Nacos 配置清单

## Data ID 命名规范

```
{application}-{profile}.yml
例如: user-service-dev.yml
```

## 需要创建的配置

### 1. 共享配置 (SHARED_GROUP)

| Data ID | 说明 |
|---------|------|
| shared-config.yml | 共享配置 (数据库、Eureka) |

### 2. 应用配置 (DEFAULT_GROUP)

| Data ID | 对应服务 |
|---------|---------|
| gateway-dev.yml | Gateway |
| gateway-prod.yml | Gateway 生产环境 |
| user-service-dev.yml | User Service |
| user-service-prod.yml | User Service 生产环境 |
| config-service-dev.yml | Config Service |
| ops-service-dev.yml | Ops Service |

## 配置内容示例

### shared-config.yml

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

### user-service-dev.yml

```yaml
server:
  port: 8081

spring:
  application:
    name: user-service

jwt:
  secret: ${JWT_SECRET:UserServiceJWTSecretKey2024}
  expiration: 1800000
  refresh-expiration: 604800000

logging:
  level:
    com.example.user: DEBUG
```

### gateway-dev.yml

```yaml
server:
  port: 8080

spring:
  application:
    name: gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: user-service
              uri: http://localhost:8081
              predicates:
                - Path=/user/**
            - id: config-service
              uri: http://localhost:8082
              predicates:
                - Path=/config/**

jwt:
  secret: ${JWT_SECRET:GatewayJWTSecretKey2024}

logging:
  level:
    org.springframework.cloud.gateway: DEBUG
```

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| NACOS_HOST | Nacos 服务器地址 | localhost |
| NACOS_PORT | Nacos 端口 | 8848 |
| NACOS_USERNAME | Nacos 用户名 | nacos |
| NACOS_PASSWORD | Nacos 密码 | nacos |
| NACOS_NAMESPACE | 命名空间 | public |
| NACOS_GROUP | 配置组 | DEFAULT_GROUP |

## 启用步骤

1. 部署 Nacos Server
2. 在 Nacos 控制台创建配置
3. 在各服务 bootstrap.yml 中取消注释 Nacos 配置
4. 重启服务
