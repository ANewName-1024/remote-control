# 配置服务设计文档

## 1. 设计目标

增强配置服务，支持以下能力：
- 国密算法支持（SM2/SM3/SM4）
- 软件根/硬件根密钥管理
- OpenClaw 配置存储

---

## 2. 国密算法支持

### 2.1 支持的算法

| 算法 | 用途 | 说明 |
|------|------|------|
| SM2 | 非对称加密 | 替代 RSA，用于密钥交换 |
| SM3 | 摘要算法 | 替代 MD5/SHA256 |
| SM4 | 对称加密 | 替代 AES，用于数据加密 |

### 2.2 接口设计

```java
/**
 * 国密算法服务接口
 */
public interface GmAlgorithmService {
    
    // SM2 非对称加密
    String sm2Encrypt(String data, String publicKey);
    String sm2Decrypt(String encryptedData, String privateKey);
    KeyPair sm2GenerateKeyPair();
    
    // SM3 摘要
    String sm3Digest(String data);
    boolean sm3Verify(String data, String digest);
    
    // SM4 对称加密
    String sm4Encrypt(String data, String key);
    String sm4Decrypt(String encryptedData, String key);
    String sm4GenerateKey();
}
```

### 2.3 配置示例

```yaml
encryption:
  algorithm: SM4  # SM4 / AES
  mode: CBC       # CBC / GCM
  padding: PKCS5Padding
  key-length: 128
  
gm:
  enabled: true
  root-type: SOFTWARE  # SOFTWARE / HARDWARE
```

---

## 3. 密钥管理

### 3.1 密钥类型

```
┌─────────────────────────────────────────────────────────────┐
│                      密钥管理体系                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   根密钥 (Root Key)                   │   │
│  │  - 软件根密钥: 加密存储在安全文件中                    │   │
│  │  - 硬件根密钥: 存储在 HSM/TFM 硬件设备中              │   │
│  └─────────────────────────────────────────────────────┘   │
│                         │                                   │
│                         ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  工作密钥 (Working Key)               │   │
│  │  - 由根密钥加密保护                                   │   │
│  │  - 用于实际数据加密                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 密钥存储策略

| 类型 | 存储方式 | 安全性 | 性能 |
|------|---------|--------|------|
| **软件根密钥** | 加密文件/环境变量 | 中 | 高 |
| **硬件根密钥** | HSM/TFM 设备 | 高 | 中 |
| **工作密钥** | 内存，周期性轮换 | 高 | 高 |

### 3.3 接口设计

```java
/**
 * 密钥管理服务
 */
public interface KeyManagementService {
    
    // 密钥生命周期
    void generateRootKey(KeyType type);           // 生成根密钥
    void backupRootKey(String path);              // 备份根密钥
    void restoreRootKey(String path);              // 恢复根密钥
    
    // 工作密钥
    String generateWorkingKey();                   // 生成工作密钥
    void rotateWorkingKey();                       // 轮换工作密钥
    String getActiveWorkingKey();                  // 获取当前工作密钥
    
    // 硬件密钥 (HSM)
    boolean isHardwareKeyAvailable();              // 检查硬件是否可用
    String encryptWithHardware(String data);       // 硬件加密
    String decryptWithHardware(String data);       // 硬件解密
}

public enum KeyType {
    SOFTWARE,   // 软件根密钥
    HARDWARE    // 硬件根密钥 (HSM)
}
```

---

## 4. OpenClaw 配置存储

### 4.1 配置模型

```java
/**
 * OpenClaw 配置实体
 */
@Entity
@Table(name = "openclaw_config")
public class OpenClawConfig {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(name = "config_key", unique = true, nullable = false)
    private String configKey;
    
    @Column(name = "config_value", columnDefinition = "TEXT")
    private String configValue;
    
    @Column(name = "config_type")
    @Enumerated(EnumType.STRING)
    private ConfigType configType;
    
    @Column(name = "encryption_algorithm")
    private String encryptionAlgorithm;  // SM4 / AES
    
    @Column(name = "key_id")
    private String keyId;                 // 使用的密钥 ID
    
    @Column(name = "is_encrypted")
    private Boolean isEncrypted;
    
    @Column(name = "description")
    private String description;
    
    @Column(name = "created_time")
    private LocalDateTime createdTime;
    
    @Column(name = "updated_time")
    private LocalDateTime updatedTime;
    
    public enum ConfigType {
        CREDENTIAL,      // 凭证 (API Key, Token)
        SECRET,          // 密钥 (密码, 证书)
        PARAMETER,       // 参数配置
        ENVIRONMENT,      // 环境变量
        GATEWAY,         // 网关配置
        EXTENSION,        // 扩展配置
        SKILL,           // 技能配置
        MEMORY           // 记忆配置
    }
}
```

### 4.2 OpenClaw 特有配置

| 配置类型 | 示例 | 加密方式 |
|---------|------|---------|
| 网关凭证 | webhook URL, bot token | SM4 加密 |
| 扩展配置 | Feishu App ID/Secret | SM4 加密 |
| 技能配置 | skill enabled, params | 可选加密 |
| 认证配置 | JWT secret, AK/SK | SM4 加密 |
| 记忆配置 | memory settings | 不加密 |

### 4.2 存储服务接口

```java
/**
 * OpenClaw 配置服务
 */
public interface OpenClawConfigService {
    
    // 配置 CRUD
    OpenClawConfig save(String key, String value, ConfigType type);
    Optional<OpenClawConfig> get(String key);
    List<OpenClawConfig> getByType(ConfigType type);
    void delete(String key);
    
    // 加密配置
    String getEncryptedValue(String key);
    void setEncryptedValue(String key, String value, String algorithm);
    
    // 批量操作
    Map<String, String> getAllConfigs();
    void importConfigs(Map<String, String> configs);
    
    // 密钥轮换
    void reEncryptAll(String newAlgorithm);
}
```

---

## 5. 架构设计

### 5.1 模块结构

```
config-service/
├── src/main/java/com/example/config/
│   ├── ConfigServiceApplication.java
│   │
│   ├── controller/
│   │   ├── ConfigController.java         # 通用配置
│   │   ├── OpenClawConfigController.java # OpenClaw 配置
│   │   └── AdminController.java          # 密钥管理
│   │
│   ├── service/
│   │   ├── ConfigService.java            # 配置服务
│   │   ├── OpenClawConfigService.java    # OpenClaw 配置
│   │   ├── GmAlgorithmService.java       # 国密算法
│   │   └── KeyManagementService.java    # 密钥管理
│   │
│   ├── security/
│   │   ├── GmCryptUtil.java             # 国密工具类
│   │   ├── KeyStoreManager.java          # 密钥库管理
│   │   └── HsmClient.java                # 硬件密钥客户端
│   │
│   ├── entity/
│   │   ├── SysConfig.java                # 系统配置
│   │   ├── OpenClawConfig.java           # OpenClaw 配置
│   │   └── KeyInfo.java                  # 密钥信息
│   │
│   └── repository/
│       ├── SysConfigRepository.java
│       ├── OpenClawConfigRepository.java
│       └── KeyInfoRepository.java
```

### 5.2 依赖

```xml
<!-- 国密算法支持 -->
<dependency>
    <groupId>org.bouncycastle</groupId>
    <artifactId>bcprov-jdk15on</artifactId>
    <version>1.70</version>
</dependency>

<!-- 硬件密钥支持 (可选) -->
<dependency>
    <groupId>com.huawei.cloud</groupId>
    <artifactId>hcs-sdk</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>

<!-- Spring Cloud Config -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
```

---

## 6. API 接口

### 6.1 OpenClaw 配置接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /openclaw/config/{key} | 获取配置 |
| POST | /openclaw/config | 创建配置 |
| PUT | /openclaw/config/{key} | 更新配置 |
| DELETE | /openclaw/config/{key} | 删除配置 |
| GET | /openclaw/config/type/{type} | 按类型获取 |
| POST | /openclaw/config/encrypt | 加密配置 |
| POST | /openclaw/config/decrypt | 解密配置 |

### 6.2 密钥管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /admin/key/generate | 生成根密钥 |
| POST | /admin/key/rotate | 轮换工作密钥 |
| GET | /admin/key/status | 密钥状态 |
| POST | /admin/key/backup | 备份密钥 |
| POST | /admin/key/restore | 恢复密钥 |

---

## 7. 安全考虑

### 7.1 密钥保护

- 根密钥使用 SM4 加密存储
- 工作密钥定期轮换（默认 90 天）
- 硬件密钥使用 HSM/TFM 保护

### 7.2 访问控制

- 配置读取需要认证
- 敏感配置需要管理员权限
- 操作密钥需要多因素认证

### 7.3 审计日志

- 所有配置变更记录审计日志
- 密钥操作记录详细日志
- 支持合规审计

---

## 8. 部署配置

### 8.1 环境变量

```bash
# 加密配置
ENCRYPTION_ALGORITHM=SM4
ROOT_KEY_TYPE=SOFTWARE  # 或 HARDWARE

# 硬件密钥 (可选)
HSM_ENABLED=false
HSM_CONFIG_PATH=/etc/openclaw/hsm.conf

# 密钥文件 (软件根密钥)
ROOT_KEY_FILE=/etc/openclaw/root.key
WORKING_KEY_DIR=/var/openclaw/keys/
```

### 8.2 初始化

首次部署需要：
1. 生成根密钥
2. 初始化工作密钥
3. 导入 OpenClaw 基础配置
