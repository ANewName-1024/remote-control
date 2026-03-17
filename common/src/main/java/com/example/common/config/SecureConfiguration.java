package com.example.common.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;

/**
 * 敏感配置管理器
 * 支持从环境变量、Vault、配置中心加载敏感信息
 */
@Configuration
@EnableConfigurationProperties(SecureProperties.class)
public class SecureConfiguration {

    private static final Logger logger = LoggerFactory.getLogger(SecureConfiguration.class);
    private static final String ALGORITHM = "AES/GCM/NoPadding";

    private final SecureProperties secureProperties;

    public SecureConfiguration(SecureProperties secureProperties) {
        this.secureProperties = secureProperties;
    }

    /**
     * 获取解密后的数据库密码
     */
    public String getDecryptedDatabasePassword() {
        return decryptValue(secureProperties.getDatabase().getPassword());
    }

    /**
     * 获取解密后的 JWT 密钥
     */
    public String getDecryptedJwtSecret() {
        return decryptValue(secureProperties.getJwt().getSecret());
    }

    /**
     * 解密配置值
     * 支持格式：
     * 1. {cipher}Base64Value - AES-256-GCM 加密值
     * 2. {vault}key - 从 Vault 获取
     * 3. plain value - 直接返回
     */
    public String decryptValue(String value) {
        if (value == null || value.isEmpty()) {
            return value;
        }

        // 检查是否加密
        if (value.startsWith("{cipher}")) {
            return decryptAes(value.substring(8));
        }

        if (value.startsWith("{vault}")) {
            // 从 Vault 获取 (需要集成 Vault)
            logger.warn("Vault 集成未实现，请使用环境变量或配置中心");
            return null;
        }

        // 明文返回
        return value;
    }

    /**
     * 加密配置值
     */
    public String encryptValue(String plainValue) {
        if (plainValue == null || plainValue.isEmpty()) {
            return plainValue;
        }

        String masterKey = secureProperties.getMasterKey();
        if (masterKey == null || masterKey.isEmpty()) {
            logger.warn("未配置加密密钥，无法加密配置值");
            return plainValue;
        }

        return "{cipher}" + encryptAes(plainValue, masterKey);
    }

    /**
     * AES-256-GCM 解密
     */
    private String decryptAes(String encryptedValue) {
        try {
            String masterKey = secureProperties.getMasterKey();
            if (masterKey == null) {
                throw new IllegalStateException("解密密钥未配置");
            }

            byte[] keyBytes = deriveKey(masterKey, "decrypt");
            SecretKeySpec keySpec = new SecretKeySpec(keyBytes, "AES");

            // 解析加密值 (格式: Base64(iv):Base64(encrypted))
            String[] parts = encryptedValue.split(":");
            if (parts.length != 2) {
                throw new IllegalArgumentException("加密值格式错误");
            }

            byte[] iv = Base64.getDecoder().decode(parts[0]);
            byte[] encrypted = Base64.getDecoder().decode(parts[1]);

            Cipher cipher = Cipher.getInstance(ALGORITHM);
            GCMParameterSpec paramSpec = new GCMParameterSpec(128, iv);
            cipher.init(Cipher.DECRYPT_MODE, keySpec, paramSpec);

            byte[] decrypted = cipher.doFinal(encrypted);
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (Exception e) {
            logger.error("解密失败", e);
            throw new RuntimeException("配置值解密失败", e);
        }
    }

    /**
     * AES-256-GCM 加密
     */
    private String encryptAes(String plainValue, String masterKey) {
        try {
            byte[] keyBytes = deriveKey(masterKey, "encrypt");

            // 生成随机 IV
            byte[] iv = new byte[12];
            new SecureRandom().nextBytes(iv);

            SecretKeySpec keySpec = new SecretKeySpec(keyBytes, "AES");

            Cipher cipher = Cipher.getInstance(ALGORITHM);
            GCMParameterSpec paramSpec = new GCMParameterSpec(128, iv);
            cipher.init(Cipher.ENCRYPT_MODE, keySpec, paramSpec);

            byte[] encrypted = cipher.doFinal(plainValue.getBytes(StandardCharsets.UTF_8));

            // 返回格式: Base64(iv):Base64(encrypted)
            return Base64.getEncoder().encodeToString(iv) + ":" 
                 + Base64.getEncoder().encodeToString(encrypted);
        } catch (Exception e) {
            logger.error("加密失败", e);
            throw new RuntimeException("配置值加密失败", e);
        }
    }

    /**
     * 派生密钥 (简化版，实际应使用 HKDF)
     */
    private byte[] deriveKey(String masterKey, String purpose) {
        try {
            String combined = masterKey + ":" + purpose;
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            return digest.digest(combined.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new RuntimeException("密钥派生失败", e);
        }
    }

    /**
     * 配置验证
     */
    @Bean
    @ConditionalOnMissingBean
    public Map<String, Object> securePropertiesValidator() {
        logger.info("========== 敏感配置加载 ==========");
        
        if (secureProperties.getMasterKey() != null && !secureProperties.getMasterKey().isEmpty()) {
            logger.info("✓ 加密密钥已配置");
        } else {
            logger.warn("⚠ 加密密钥未配置 (SECURE_MASTER_KEY)");
        }

        if (secureProperties.getDatabase().getPassword() != null) {
            logger.info("✓ 数据库密码已配置");
        }

        if (secureProperties.getJwt().getSecret() != null) {
            logger.info("✓ JWT 密钥已配置");
        }

        return Map.of();
    }
}
