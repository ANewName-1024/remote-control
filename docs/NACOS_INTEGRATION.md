# Nacos 配置中心集成方案

## 1. 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nacos Server (8848)                          │
│  ┌───────────────────────────────────────────────────────────┐│
│  │  配置管理 GUI                                              ││
│  │  ├── user-service-dev.yml                                 ││
│  │  ├── gateway-prod.yml                                     ││
│  │  └── shared-config.yml                                    ││
│  └───────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
           ▲                    ▲                    ▲
           │                    │                    │
    ┌──────┴──────┐     ┌─────┴─────┐       ┌─────┴─────┐
    │   Gateway   │     │   User    │       │   Config  │
    │   (8080)   │     │  (8081)   │       │  (8082)   │
    └─────────────┘     └───────────┘       └───────────┘

现有 config-service 功能保留:
├── 配置存储在 PostgreSQL (sys_config, openclaw_config)
├── REST API 管理配置
└── 国密加密能力
```

## 2. Nacos 部署

### 方式 A: Docker 部署 (推荐)

```bash
# 启动 Nacos
docker run -d --name nacos -p 8848:8848 -p 9848:9848 \
  -e MODE=standalone \
  -e SPRING_DATASOURCE_PLATFORM=postgresql \
  -e DB_URL=jdbc:postgresql://8.137.116.121:8432/nacos_config \
  -e DB_USER=business \
  -e DB_PASSWORD=NewPass2024 \
  nacos/nacos-server:v2.3.2
```

### 方式 B: 直接运行

```bash
# 下载并解压
wget https://github.com/alibaba/nacos/releases/download/v2.3.2/nacos-server-2.3.2.tar.gz
tar -xvf nacos-server-2.3.2.tar.gz

# 配置数据库
# 修改 conf/application.properties

# 启动
cd nacos/bin
./startup.sh -m standalone
```

## 3. 各服务集成

### 3.1 添加依赖 (pom.xml)

```xml
<!-- Nacos Config -->
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    <version>2023.0.1.2</version>
</dependency>
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-nacos-config</artifactId>
    <version>2023.0.1.2</version>
</dependency>
```

### 3.2 配置 bootstrap.yml

```yaml
spring:
  application:
    name: user-service
  cloud:
    nacos:
      server-addr: localhost:8848
      username: nacos
      password: nacos
      config:
        namespace: public
        group: DEFAULT_GROUP
        file-extension: yml
        refresh-enabled: true
        # 共享配置
        shared-configs:
          - data-id: shared-config.yml
            group: SHARED_GROUP
            refresh: true
```

### 3.3 启用动态刷新

```java
@RestController
@RefreshScope  // 启用动态刷新
public class UserController {
    @Value("${user.service.timeout:5000}")
    private int timeout;
    
    // 配置变更时自动更新
}
```

## 4. 配置示例

### Nacos 中的配置

**Data ID**: `user-service-dev.yml`
**Group**: `DEFAULT_GROUP`

```yaml
spring:
  datasource:
    url: jdbc:postgresql://8.137.116.121:8432/business_db
    username: business
    password: ${DB_PASSWORD:NewPass2024}

jwt:
  secret: ${JWT_SECRET:UserServiceJWTSecretKey2024}
  expiration: 1800000

eureka:
  client:
    service-url:
      defaultZone: http://admin:EurekaNew2024@8.137.116.121:9000/eureka/
```

## 5. 实施步骤

### Step 1: 部署 Nacos Server

```bash
# 方式1: Docker
docker run -d --name nacos -p 8848:8848 -p 9848:9848 \
  -e MODE=standalone \
  nacos/nacos-server:v2.3.2
```

### Step 2: 各服务添加 Nacos 依赖

### Step 3: 配置 Nacos 连接

### Step 4: 将配置迁移到 Nacos

### Step 5: 测试动态刷新

## 6. 保留现有能力

现有 config-service 的能力保留：

| 能力 | 保留方式 | 说明 |
|------|----------|------|
| 数据库存储 | 原有表 | sys_config, openclaw_config |
| REST API | 原有接口 | /api/config/* |
| 国密加密 | 原有模块 | GmCryptUtil |
| 配置历史 | 原有表 | config_history |

Nacos 作为配置中心获取配置，config-service 作为配置管理 API。

## 7. 服务端口规划

| 服务 | 端口 |
|------|------|
| Gateway | 8080 |
| user-service | 8081 |
| config-service | 8082 |
| **Nacos** | **8848** |
| PostgreSQL | 8432 |
| Eureka | 9000 |

## 8. 配置优先级

```
Nacos 配置 > 本地配置 > 默认值
```

可以通过 `spring.cloud.nacos.config.priority` 调整优先级。
