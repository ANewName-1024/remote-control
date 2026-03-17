# Config Service 数据表设计

## 概述

config-service 使用 JPA 自动建表，数据库为 PostgreSQL (business_db)。

## 数据表

### 1. sys_config - 系统配置表

```sql
CREATE TABLE sys_config (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    data_type VARCHAR(50) NOT NULL,  -- STRING, NUMBER, BOOLEAN, JSON
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

---

### 2. config_history - 配置变更历史表

```sql
CREATE TABLE config_history (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(255) NOT NULL,
    operation_type VARCHAR(50) NOT NULL,  -- CREATE, UPDATE, DELETE
    old_value TEXT,
    new_value TEXT,
    operation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operator VARCHAR(100),
    reason VARCHAR(500)
);

CREATE INDEX idx_config_history_key ON config_history(config_key);
CREATE INDEX idx_config_history_time ON config_history(operation_time);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| configKey | String | 配置键 |
| operationType | Enum | 操作类型 (CREATE/UPDATE/DELETE) |
| oldValue | String | 旧值 |
| newValue | String | 新值 |
| operationTime | LocalDateTime | 操作时间 |
| operator | String | 操作人 |
| reason | String | 变更原因 |

---

### 3. openclaw_config - OpenClaw 配置表

```sql
CREATE TABLE openclaw_config (
    id BIGSERIAL PRIMARY KEY,
    config_type VARCHAR(100) NOT NULL,  -- gateway, feishu, weather, etc.
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

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| configType | String | 配置类型 (gateway/feishu/weather...) |
| configKey | String | 配置键 |
| configValue | String | 配置值 |
| encrypted | Boolean | 是否加密存储 |
| description | String | 描述 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |
| createdBy | String | 创建人 |
| updatedBy | String | 更新人 |

---

### 4. config_user - 配置服务用户表 (可选，用于服务间认证)

```sql
CREATE TABLE config_user (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    roles VARCHAR(500),  -- comma-separated roles
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_config_user_username ON config_user(username);
```

---

## 建表策略

### 开发环境
```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: update  # 自动更新表结构
```

### 生产环境
```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate  # 仅验证，不修改
```
生产环境应手动执行 SQL 建表脚本。

## ER 关系

```
┌─────────────────┐     ┌──────────────────────┐
│    sys_config   │     │   config_history     │
├─────────────────┤     ├──────────────────────┤
│ id (PK)         │────<│ config_key (FK)     │
│ config_key      │     │ operation_type       │
│ config_value    │     │ old_value            │
│ data_type       │     │ new_value            │
│ description     │     │ operation_time       │
└─────────────────┘     └──────────────────────┘

┌─────────────────────┐
│  openclaw_config    │
├─────────────────────┤
│ id (PK)             │
│ config_type         │
│ config_key          │
│ config_value        │
│ encrypted           │
└─────────────────────┘
```

## 数据类型枚举

### DataType (sys_config)
- `STRING` - 字符串
- `NUMBER` - 数字
- `BOOLEAN` - 布尔值
- `JSON` - JSON 格式

### OperationType (config_history)
- `CREATE` - 创建
- `UPDATE` - 更新
- `DELETE` - 删除
