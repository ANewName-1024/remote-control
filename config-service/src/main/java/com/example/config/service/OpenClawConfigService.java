package com.example.config.service;

import com.example.config.entity.OpenClawConfig;
import com.example.config.repository.OpenClawConfigRepository;
import com.example.config.security.KeyManagementService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * OpenClaw 配置服务
 */
@Service
public class OpenClawConfigService {

    private static final Logger log = LoggerFactory.getLogger(OpenClawConfigService.class);

    @Value("${encryption.default-algorithm:SM4}")
    private String defaultAlgorithm;

    private final OpenClawConfigRepository repository;
    private final KeyManagementService keyManagementService;

    public OpenClawConfigService(OpenClawConfigRepository repository,
                                  KeyManagementService keyManagementService) {
        this.repository = repository;
        this.keyManagementService = keyManagementService;
    }

    // ==================== 配置 CRUD ====================

    /**
     * 保存配置
     */
    @Transactional
    public OpenClawConfig save(String key, String value, OpenClawConfig.ConfigType type) {
        return save(key, value, type, false, null);
    }

    /**
     * 保存配置（可指定加密）
     */
    @Transactional
    public OpenClawConfig save(String key, String value, OpenClawConfig.ConfigType type,
                               boolean encrypt, String algorithm) {
        Optional<OpenClawConfig> existing = repository.findByConfigKey(key);
        
        OpenClawConfig config;
        if (existing.isPresent()) {
            config = existing.get();
        } else {
            config = new OpenClawConfig();
            config.setConfigKey(key);
            config.setCreatedTime(LocalDateTime.now());
        }

        // 处理加密
        if (encrypt || isSecretType(type)) {
            config.setIsEncrypted(true);
            config.setEncryptionAlgorithm(algorithm != null ? algorithm : defaultAlgorithm);
            config.setKeyId(keyManagementService.getWorkingKeyId());
            config.setConfigValue(keyManagementService.encrypt(value));
        } else {
            config.setIsEncrypted(false);
            config.setConfigValue(value);
        }

        config.setConfigType(type);
        config.setUpdatedTime(LocalDateTime.now());

        return repository.save(config);
    }

    /**
     * 获取配置
     */
    public Optional<OpenClawConfig> get(String key) {
        return repository.findByConfigKey(key);
    }

    /**
     * 获取配置值（自动解密）
     */
    public String getValue(String key) {
        Optional<OpenClawConfig> config = repository.findByConfigKey(key);
        
        if (config.isEmpty()) {
            return null;
        }

        OpenClawConfig c = config.get();
        if (Boolean.TRUE.equals(c.getIsEncrypted())) {
            return keyManagementService.decrypt(c.getConfigValue());
        }

        return c.getConfigValue();
    }

    /**
     * 按类型获取配置
     */
    public List<OpenClawConfig> getByType(OpenClawConfig.ConfigType type) {
        return repository.findByConfigType(type);
    }

    /**
     * 获取所有配置（解密后的值）
     */
    public Map<String, String> getAllConfigs() {
        List<OpenClawConfig> configs = repository.findAllActive();
        Map<String, String> result = new HashMap<>();

        for (OpenClawConfig config : configs) {
            String value;
            if (Boolean.TRUE.equals(config.getIsEncrypted())) {
                try {
                    value = keyManagementService.decrypt(config.getConfigValue());
                } catch (Exception e) {
                    log.error("解密配置失败: {}", config.getConfigKey(), e);
                    value = "***解密失败***";
                }
            } else {
                value = config.getConfigValue();
            }
            result.put(config.getConfigKey(), value);
        }

        return result;
    }

    /**
     * 删除配置
     */
    @Transactional
    public void delete(String key) {
        repository.findByConfigKey(key).ifPresent(config -> {
            config.setIsDeleted(1);
            config.setUpdatedTime(LocalDateTime.now());
            repository.save(config);
        });
    }

    // ==================== 加密操作 ====================

    /**
     * 加密配置
     */
    @Transactional
    public String encryptValue(String key, String algorithm) {
        Optional<OpenClawConfig> configOpt = repository.findByConfigKey(key);
        
        if (configOpt.isEmpty()) {
            throw new RuntimeException("配置不存在: " + key);
        }

        OpenClawConfig config = configOpt.get();
        
        if (Boolean.TRUE.equals(config.getIsEncrypted())) {
            return config.getConfigValue(); // 已经是加密的
        }

        // 加密并保存
        String encrypted = keyManagementService.encrypt(config.getConfigValue());
        config.setConfigValue(encrypted);
        config.setIsEncrypted(true);
        config.setEncryptionAlgorithm(algorithm != null ? algorithm : defaultAlgorithm);
        config.setKeyId(keyManagementService.getWorkingKeyId());
        config.setUpdatedTime(LocalDateTime.now());
        
        repository.save(config);
        
        return encrypted;
    }

    /**
     * 解密配置
     */
    @Transactional
    public String decryptValue(String key) {
        Optional<OpenClawConfig> configOpt = repository.findByConfigKey(key);
        
        if (configOpt.isEmpty()) {
            throw new RuntimeException("配置不存在: " + key);
        }

        OpenClawConfig config = configOpt.get();
        
        if (!Boolean.TRUE.equals(config.getIsEncrypted())) {
            return config.getConfigValue(); // 未加密
        }

        // 解密并保存
        String decrypted = keyManagementService.decrypt(config.getConfigValue());
        config.setConfigValue(decrypted);
        config.setIsEncrypted(false);
        config.setEncryptionAlgorithm(null);
        config.setKeyId(null);
        config.setUpdatedTime(LocalDateTime.now());
        
        repository.save(config);
        
        return decrypted;
    }

    /**
     * 重新加密所有配置
     */
    @Transactional
    public void reEncryptAll(String newAlgorithm) {
        List<OpenClawConfig> encryptedConfigs = repository.findByIsEncryptedTrue();
        
        for (OpenClawConfig config : encryptedConfigs) {
            try {
                // 解密
                String decrypted = keyManagementService.decrypt(config.getConfigValue());
                
                // 使用新密钥重新加密
                String reEncrypted = keyManagementService.encrypt(decrypted);
                
                config.setConfigValue(reEncrypted);
                config.setEncryptionAlgorithm(newAlgorithm);
                config.setKeyId(keyManagementService.getWorkingKeyId());
                config.setUpdatedTime(LocalDateTime.now());
                
                repository.save(config);
                
                log.info("重新加密配置: {}", config.getConfigKey());
            } catch (Exception e) {
                log.error("重新加密配置失败: {}", config.getConfigKey(), e);
            }
        }
    }

    // ==================== 批量操作 ====================

    /**
     * 批量导入配置
     */
    @Transactional
    public void importConfigs(Map<String, String> configs) {
        for (Map.Entry<String, String> entry : configs.entrySet()) {
            save(entry.getKey(), entry.getValue(), OpenClawConfig.ConfigType.PARAMETER);
        }
    }

    /**
     * 初始化默认配置
     */
    public void initDefaultConfigs() {
        // 网关配置
        save("gateway.enabled", "true", OpenClawConfig.ConfigType.GATEWAY);
        save("gateway.port", "8080", OpenClawConfig.ConfigType.GATEWAY);
        
        // 扩展配置
        save("extension.feishu.enabled", "false", OpenClawConfig.ConfigType.EXTENSION);
        save("extension.telegram.enabled", "false", OpenClawConfig.ConfigType.EXTENSION);
        
        // 技能配置
        save("skill.weather.enabled", "true", OpenClawConfig.ConfigType.SKILL);
        save("skill.github.enabled", "false", OpenClawConfig.ConfigType.SKILL);
        
        // 记忆配置
        save("memory.daily.enabled", "true", OpenClawConfig.ConfigType.MEMORY);
        save("memory.longterm.enabled", "true", OpenClawConfig.ConfigType.MEMORY);
        
        log.info("OpenClaw 默认配置初始化完成");
    }

    // ==================== 工具方法 ====================

    private boolean isSecretType(OpenClawConfig.ConfigType type) {
        return type == OpenClawConfig.ConfigType.CREDENTIAL ||
               type == OpenClawConfig.ConfigType.SECRET;
    }
}
