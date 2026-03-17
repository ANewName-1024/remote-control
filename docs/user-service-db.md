# User Service 数据表设计

## 概述

user-service 是系统的用户认证和授权中心，使用 RBAC 模型 + OIDC 协议。

## 数据表

### 1. users - 用户表

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255),
    password VARCHAR(255) NOT NULL,  -- BCrypt 加密
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| username | String | 用户名，唯一 |
| email | String | 邮箱 |
| password | String | BCrypt 加密密码 |
| enabled | Boolean | 账户是否启用 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

---

### 2. roles - 角色表

```sql
CREATE TABLE roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_roles_name ON roles(name);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| name | String | 角色名（如 ROLE_ADMIN, ROLE_USER）|
| description | String | 描述 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

---

### 3. permissions - 权限表

```sql
CREATE TABLE permissions (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,  -- 格式: resource:action
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_permissions_name ON permissions(name);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键，自增 |
| name | String | 权限名（格式：resource:action）|
| description | String | 描述 |
| createdAt | LocalDateTime | 创建时间 |

**权限命名规范**：
- `user:read` - 查看用户
- `user:write` - 创建/修改用户
- `user:delete` - 删除用户
- `config:read` - 读取配置
- `config:write` - 修改配置
- `admin:manage` - 管理权限

---

### 4. user_roles - 用户角色关联表

```sql
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX idx_user_roles_user ON user_roles(user_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);
```

---

### 5. role_permissions - 角色权限关联表

```sql
CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role_id);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_id);
```

---

## OIDC 相关表

### 6. oidc_clients - OIDC 客户端注册表

```sql
CREATE TABLE oidc_clients (
    id BIGSERIAL PRIMARY KEY,
    client_id VARCHAR(100) NOT NULL UNIQUE,
    client_secret VARCHAR(255),  -- 可加密存储
    client_name VARCHAR(255),
    client_uri VARCHAR(500),
    redirect_uris TEXT,  -- 多个 URI 逗号分隔
    grant_types TEXT,    -- authorization_code, client_credentials, refresh_token
    response_types TEXT, -- code, token, id_token
    scope TEXT,          -- openid, profile, email
    token_endpoint_auth_method VARCHAR(50), -- client_secret_basic, client_secret_post, none
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_oidc_clients_client_id ON oidc_clients(client_id);
```

**实体字段**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 主键 |
| clientId | String | 客户端 ID |
| clientSecret | String | 客户端密钥 |
| clientName | String | 客户端名称 |
| clientUri | String | 客户端首页 |
| redirectUris | String | 回调 URI 列表 |
| grantTypes | String | 支持的授权类型 |
| responseTypes | String | 响应类型 |
| scope | String | 权限范围 |
| tokenEndpointAuthMethod | String | Token 端点认证方式 |
| enabled | Boolean | 是否启用 |
| createdAt | LocalDateTime | 创建时间 |
| updatedAt | LocalDateTime | 更新时间 |

---

### 7. oidc_authorization_codes - OIDC 授权码表

```sql
CREATE TABLE oidc_authorization_codes (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(255) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id VARCHAR(100) NOT NULL,
    redirect_uri VARCHAR(500) NOT NULL,
    scope TEXT,
    nonce VARCHAR(500),
    state VARCHAR(500),
    code_challenge VARCHAR(255),
    code_challenge_method VARCHAR(10),  -- S256, plain
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_oidc_codes_code ON oidc_authorization_codes(code);
CREATE INDEX idx_oidc_codes_user ON oidc_authorization_codes(user_id);
CREATE INDEX idx_oidc_codes_expires ON oidc_authorization_codes(expires_at);
```

**字段说明**：
| 字段 | 类型 | 说明 |
|------|------|------|
| code | String | 授权码（一次性）|
| userId | Long | 用户 ID |
| clientId | String | 客户端 ID |
| redirectUri | String | 回调 URI |
| scope | String | 请求的 scope |
| nonce | String | 防重放 nonce |
| state | String | CSRF 防护 state |
| codeChallenge | String | PKCE code challenge |
| codeChallengeMethod | String | PKCE 方法 (S256/plain) |
| expiresAt | LocalDateTime | 过期时间 |
| used | Boolean | 是否已使用 |

---

## ER 关系图

```
┌─────────────┐       ┌─────────────┐       ┌──────────────┐
│    users    │       │    roles    │       │ permissions  │
├─────────────┤       ├─────────────┤       ├──────────────┤
│ id (PK)     │──────<│ id (PK)     │──────<│ id (PK)      │
│ username    │       │ name        │       │ name         │
│ email       │       │ description │       │ description  │
│ password    │       └─────────────┘       └──────────────┘
│ enabled     │             │
└─────────────┘             │
       │                    │
       │    ┌───────────────┘
       │    │
       ▼    ▼
┌───────────────┐
│  user_roles   │
├───────────────┤
│ user_id (FK)  │
│ role_id (FK)  │
└───────────────┘

┌──────────────────┐     ┌────────────────────────────┐
│  oidc_clients    │     │ oidc_authorization_codes  │
├──────────────────┤     ├────────────────────────────┤
│ id (PK)          │     │ id (PK)                   │
│ client_id        │     │ code                      │
│ client_secret    │────<│ user_id (FK)              │
│ client_name      │     │ client_id                 │
│ redirect_uris    │     │ redirect_uri              │
│ grant_types      │     │ scope                     │
└──────────────────┘     │ nonce                     │
                         │ code_challenge            │
                         │ expires_at                │
                         │ used                      │
                         └────────────────────────────┘
```

## 初始化数据

### 默认角色
```sql
INSERT INTO roles (name, description) VALUES 
('ROLE_ADMIN', '系统管理员'),
('ROLE_USER', '普通用户'),
('ROLE_GUEST', '访客');
```

### 默认权限
```sql
INSERT INTO permissions (name, description) VALUES 
('user:read', '查看用户'),
('user:write', '创建/修改用户'),
('user:delete', '删除用户'),
('config:read', '读取配置'),
('config:write', '修改配置'),
('admin:manage', '系统管理');
```

### 管理员账户
```sql
-- 用户名: admin
-- 密码: (BCrypt 加密，需要通过应用创建)
INSERT INTO users (username, email, password, enabled) VALUES 
('admin', 'admin@example.com', '$2a$10$...', true);

-- 分配管理员角色
INSERT INTO user_roles (user_id, role_id) 
SELECT u.id, r.id FROM users u, roles r 
WHERE u.username = 'admin' AND r.name = 'ROLE_ADMIN';
```
