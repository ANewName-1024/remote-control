# Spring Cloud Config Server 数据库存储集成方案

## 1. 背景说明

Spring Cloud 2025.x 版本中，官方已移除 `spring-cloud-config-server-jdbc` 依赖，需要自定义实现 `EnvironmentRepository` 接口来支持数据库存储。

## 2. 方案设计

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Config Server (8082)                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  @EnableConfigServer                                     │  │
│  │  + 自定义 JdbcEnvironmentRepository                      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                            │                                    │
│                            ▼                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL Database (business_db)                        │  │
│  │  ┌─────────────────┐  ┌─────────────────────────────┐   │  │
│  │  │ config_properties│  │ config_version (可选)      │   │  │
│  │  │ (id, app, profile, label, key, value, created)   │   │  │
│  │  └─────────────────┘  └─────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           ▲                    ▲                    ▲
           │                    │                    │
    ┌──────┴──────┐     ┌─────┴─────┐       ┌─────┴─────┐
    │   Gateway   │     │   User    │       │   Ops     │
    │  (8080)    │     │ (8081)    │       │  (8083)   │
    └─────────────┘     └───────────┘       └───────────┘
```

### 2.2 数据表设计

```sql
-- 配置属性表
CREATE TABLE config_properties (
    id BIGSERIAL PRIMARY KEY,
    application VARCHAR(255) NOT NULL,  -- 应用名 (如: user-service)
    profile VARCHAR(255) NOT NULL,      -- 环境 (如: dev, prod)
    label VARCHAR(255) NOT NULL,        -- 标签 (如: master)
    key VARCHAR(255) NOT NULL,         -- 配置键
    value TEXT,                         -- 配置值
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uk_config_prop UNIQUE (application, profile, label, key)
);

-- 创建索引
CREATE INDEX idx_config_app_profile ON config_properties(application, profile);
CREATE INDEX idx_config_app_profile_label ON config_properties(application, profile, label);
```

### 2.3 核心实现

#### Step 1: 添加依赖 (config-service/pom.xml)

```xml
<dependencies>
    <!-- Spring Cloud Config Server -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    
    <!-- Spring JDBC -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    
    <!-- PostgreSQL Driver -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
    </dependency>
</dependencies>
```

#### Step 2: 自定义 JdbcEnvironmentRepository

```java
package com.example.config.repository;

import org.springframework.cloud.config.server.environment.EnvironmentRepository;
import org.springframework.cloud.config.server.environment.Environment;
import org.springframework.cloud.config.server.environment.SearchPathLocator;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.*;

@Repository
public class JdbcEnvironmentRepository implements EnvironmentRepository {

    private final JdbcTemplate jdbcTemplate;

    public JdbcEnvironmentRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Environment find(String application, String profile, String label) {
        String[] profiles = profile.split(",");
        List<String> profileList = Arrays.asList(profiles);
        
        Environment env = new Environment(application, profiles, label, null, null);
        
        // 查询配置
        for (String prof : profiles) {
            String sql = """
                SELECT key, value FROM config_properties 
                WHERE application = ? AND profile = ? AND label = ?
                """;
            
            jdbcTemplate.query(sql, (rs, rowNum) -> {
                env.add(new PropertySource("JdbcEnvironmentRepository", 
                    Map.of(rs.getString("key"), rs.getString("value"))));
                return null;
            }, application, prof, label);
        }
        
        return env;
    }
}
```

#### Step 3: 启用 Config Server

```java
package com.example.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServiceApplication.class, args);
    }
}
```

#### Step 4: 配置 application.yml

```yaml
spring:
  application:
    name: config-service
  
  cloud:
    config:
      server:
        jdbc:
          sql: SELECT key, value from config_properties where application=? and profile=? and label=?
          # 初始化数据库表
          initialize: true
          table: config_properties
  
  datasource:
    url: jdbc:postgresql://${DB_HOST:8.137.116.121}:${DB_PORT:8432}/${DB_NAME:business_db}
    username: ${DB_USERNAME:business}
    password: ${DB_PASSWORD:NewPass2024}
```

### 2.4 客户端配置

各服务添加 bootstrap.yml：

```yaml
spring:
  config:
    import: optional:configserver:http://localhost:8082
  cloud:
    config:
      uri: http://localhost:8082
      profile: dev
      label: master
      fail-fast: false
```

## 3. 替代方案

### 方案 A: 使用 Nacos (推荐)

阿里开源的配置中心，原生支持数据库存储：

```
Nacos + MySQL/PostgreSQL
├── 配置管理 (GUI)
├── 动态刷新
├── 版本管理
└── 权限控制
```

**优点**：
- 开箱即用
- GUI 管理界面
- 社区活跃
- 国产文档丰富

**缺点**：
- 需要额外部署 Nacos Server

### 方案 B: 继续使用自建配置 API (当前方案)

```java
@RestController
@RequestMapping("/api/config")
public class ConfigController {
    // 现有实现
}
```

**优点**：
- 无额外依赖
- 完全可控

**缺点**：
- 不是标准 Spring Cloud Config 协议
- 需要自行实现客户端轮询

## 4. 推荐方案

| 场景 | 推荐方案 |
|------|----------|
| 小型项目 | 继续使用自建 API (当前) |
| 中型项目 | 使用 Nacos |
| 大型项目 | Spring Cloud Config Server + Git/Vault |

## 5. 实施计划

如果选择方案 A (Nacos)：
1. 部署 Nacos Server
2. 配置 MySQL/PostgreSQL 存储
3. 迁移配置到 Nacos
4. 各服务添加 Nacos Client 依赖

如果选择继续当前方案：
1. 完善配置 API (增删改查)
2. 实现配置变更推送 (WebSocket)
3. 添加配置版本管理
