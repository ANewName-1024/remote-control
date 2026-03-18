# Config Service 数据表设计

## 概述

config-service 使用 JPA 自动建表，数据库为 PostgreSQL。

## 数据表

### 1. sys_config - 系统配置表

```sql
CREATE TABLE sys_config (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100)
);

CREATE INDEX idx_sys_config_key ON sys_config(config_key);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| configKey | String | 配置键，唯一 |
| configValue | String | 配置值 |
| dataType | Enum | 数据类型 (STRING/NUMBER/BOOLEAN/JSON) |
| description | String | 描述 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |
| createdBy | String | 创建人 |
| updatedBy | String | 更新人 |

### 2. config_history - 配置变更历史表

```sql
CREATE TABLE config_history (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    operation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operator VARCHAR(100),
    reason VARCHAR(500)
);

CREATE INDEX idx_config_history_key ON config_history(config_key);
CREATE INDEX idx_config_history_time ON config_history(operation_time);
```

### 3. openclaw_config - OpenClaw 配置表

```sql
CREATE TABLE openclaw_config (
    id BIGSERIAL PRIMARY KEY,
    config_type VARCHAR(100) NOT NULL,
    config_key VARCHAR(255) NOT NULL,
    config_value TEXT,
    encrypted BOOLEAN DEFAULT FALSE,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    
    CONSTRAINT uk_openclaw_config UNIQUE (config_type, config_key)
);

CREATE INDEX idx_openclaw_config_type ON openclaw_config(config_type);
```

## 技术栈

- Spring Boot: 3.5.0
- Spring Cloud: 2025.0.0
- Nacos: 可选集成
- 数据库: PostgreSQL 11.15
- 国密算法: SM2/SM3/SM4

## 功能特性

- REST API 配置管理
- 配置变更历史记录
- 国密加密支持
- Nacos 可选集成
