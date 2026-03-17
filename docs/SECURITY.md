# 敏感信息保护方案

## 问题分析

### 当前方案
```yaml
# application.yml
spring:
  datasource:
    password: ${DB_PASSWORD}  # 环境变量
```

**风险点**：
1. 进程启动命令可能被 history 记录
2. `ps aux` 可查看进程环境变量
3. 容器编排文件 (docker-compose.yml) 明文存储
4. CI/CD 流水线配置明文存储
5. Git 仓库可能误提交敏感信息

## 优化方案

### 方案一：配置中心 + 加密存储 (推荐)

```
┌─────────────────────────────────────────────────────────┐
│                    Spring Cloud Config                   │
│                    (配置中心服务)                         │
├─────────────────────────────────────────────────────────┤
│  1. 配置加密存储 (AES-256)                              │
│  2. 启动时从配置中心拉取                                 │
│  3. 使用 master-key 解密                                │
└─────────────────────────────────────────────────────────┘
```

**实现**：
1. 配置使用 `{cipher}encrypted-value` 格式
2. 启动时自动解密
3. master-key 通过环境变量注入

```yaml
# config-repo/application.yml
spring:
  datasource:
    password: {cipher}AQBf8mK3...  # 加密存储
```

```bash
# 启动命令 (只有 master-key 在环境变量)
java -jar app.jar --spring.cloud.config.server.encrypt.key=${MASTER_KEY}
```

---

### 方案二：Docker Secrets (容器环境)

```yaml
# docker-compose.yml
services:
  user-service:
    image: user-service:1.0.0
    secrets:
      - db_password
      - jwt_secret

secrets:
  db_password:
    file: ./secrets/db_password.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
```

**优点**：
- Docker Swarm 内置加密
- 不在容器环境变量中暴露
- 权限控制

---

### 方案三：外部密钥服务 (KMS)

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   应用服务   │ ───▶ │   KMS API    │ ───▶ │  密钥管理服务 │
│              │      │  (获取密钥)  │      │  (AWS/阿里)  │
└──────────────┘      └──────────────┘      └──────────────┘
```

**优点**：
- 集中管理
- 审计日志
- 密钥轮换
- 支持硬件安全模块 (HSM)

---

### 方案四：Vault 方案 (企业级)

```
┌──────────────┐      ┌──────────────┐
│   应用服务   │ ───▶ │    Vault     │
│              │      │  (密钥保险库) │
└──────────────┘      └──────────────┘
       │                      │
       │                      ▼
       │              ┌──────────────┐
       └─────────────▶│  数据库/文件   │
                      └──────────────┘

特点：
- 动态密钥生成
- 自动密钥轮换
- 审计日志
- 多种认证方式 (K8s SA, AppRole, LDAP)
```

---

## 推荐方案：配置中心加密 + Vault

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        开发/测试环境                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │   IDE/本地   │    │  配置中心   │    │   Vault     │   │
│  │ (config)    │    │ (加密存储)  │    │  (开发环境)  │   │
│  └─────────────┘    └─────────────┘    └─────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        生产环境                              │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │  K8s/Docker │    │  配置中心   │    │   生产Vault │   │
│  │  (Secrets) │    │ (加密存储)  │    │   (HSM)     │   │
│  └─────────────┘    └─────────────┘    └─────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 配置示例

#### 1. 配置加密工具类

```java
// 加密配置值
public class ConfigEncryptor {
    
    private static final String ALGORITHM = "AES/GCM/NoPadding";
    
    public static String encrypt(String plainText, String masterKey) {
        // 生成随机 IV
        byte[] iv = new byte[12];
        new SecureRandom().nextBytes(iv);
        
        // 使用 master-key 派生出数据加密密钥
        SecretKey key = deriveKey(masterKey, "config-encryption");
        
        // AES-GCM 加密
        Cipher cipher = Cipher.getInstance(ALGORITHM);
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(128, iv));
        byte[] encrypted = cipher.doFinal(plainText.getBytes());
        
        // 返回格式: {cipher}[Base64(iv + encrypted)]
        return "{cipher}" + Base64.getEncoder().encodeToString(iv) + ":" 
            + Base64.getEncoder().encodeToString(encrypted);
    }
    
    private static SecretKey deriveKey(String masterKey, String purpose) {
        // 使用 HKDF 派生密钥
        // ...
    }
}
```

#### 2. 配置中心配置

```yaml
# config-server/application.yml
spring:
  application:
    name: config-server
  
  cloud:
    config:
      server:
        encrypt:
          key: ${CONFIG_MASTER_KEY}  # 启动时注入
  
  security:
    user:
      password: ${CONFIG_SERVER_PASSWORD}
```

#### 3. 微服务配置

```yaml
# bootstrap.yml
spring:
  cloud:
    config:
      uri: http://config-service:8888
      username: ${CONFIG_CLIENT_USERNAME}
      password: ${CONFIG_CLIENT_PASSWORD}  # 从 Vault 获取
      
# application.yml (在配置中心)
spring:
  datasource:
    password: {cipher}AQBf8mK3...  # 加密存储
```

---

## 密钥管理矩阵

| 环境 | 存储方式 | 密钥来源 | 轮换周期 |
|------|----------|----------|----------|
| 开发 | 配置中心(加密) | 共享 master-key | 按需 |
| 测试 | 配置中心(加密) | 独立 master-key | 每月 |
| 生产 | Vault + HSM | 自动轮换 | 每周/每日 |

---

## 实施步骤

### 1. 立即可做
- [x] 删除 Git 中的敏感配置
- [x] 使用 .gitignore 排除敏感文件
- [x] 启用配置加密存储

### 2. 短期目标
- [ ] 部署 Vault (开发/测试环境)
- [ ] 集成 KMS API
- [ ] 配置 Docker Secrets

### 3. 长期目标
- [ ] 生产环境使用 HSM
- [ ] 自动化密钥轮换
- [ ] 密钥审计日志

---

## 安全检查清单

```bash
# 检查敏感信息泄露
grep -r "password\s*=" --include="*.yml" --include="*.properties" .
grep -r "secret\s*=" --include="*.yml" --include="*.properties" .
grep -r "key\s*=" --include="*.yml" --include="*.properties" .

# 检查环境变量
env | grep -i "password\|secret\|key\|token"

# 检查 Docker 环境变量
docker inspect <container> | grep -i "Env"
```

---

## 相关配置

### .gitignore 敏感文件

```
# 敏感配置
config-local.yml
application-local.yml
*.local.*

# 密钥文件
*.key
*.pem
secrets/
credentials/
```

### CI/CD 安全

```yaml
# .gitlab-ci.yml 示例
variables:
  DB_PASSWORD: $CI_REGISTRY_PASSWORD  # 从 GitLab CI 变量获取
  
script:
  - docker build --build-arg DB_PASSWORD=$DB_PASSWORD .
```

---

最后更新: 2026-03-17
