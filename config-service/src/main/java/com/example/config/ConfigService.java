package com.example.config;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Service
public class ConfigService {
    
    @Autowired
    private SysConfigRepository configRepository;
    
    @Autowired
    private ConfigHistoryRepository historyRepository;
    
    @Autowired
    private EncryptionService encryptionService;
    
    /**
     * 创建配置
     */
    @Transactional
    public SysConfig createConfig(SysConfig config, String operator) {
        // 检查key是否存在
        if (configRepository.existsByConfigKeyAndIsDeleted(config.getConfigKey(), 0)) {
            throw new RuntimeException("配置键已存在: " + config.getConfigKey());
        }
        
        // 如果标记为加密，则加密存储
        if (Boolean.TRUE.equals(config.getIsEncrypted()) || config.getDataType() == SysConfig.DataType.ENCRYPTED) {
            config.setConfigValue(encryptionService.encrypt(config.getConfigValue()));
            config.setIsEncrypted(true);
            config.setDataType(SysConfig.DataType.ENCRYPTED);
        }
        
        config.setCreatedBy(operator);
        config.setCreatedTime(LocalDateTime.now());
        config.setUpdatedBy(operator);
        config.setUpdatedTime(LocalDateTime.now());
        config.setIsDeleted(0);
        
        SysConfig saved = configRepository.save(config);
        
        // 记录历史
        saveHistory(saved.getId(), saved.getConfigKey(), null, saved.getConfigValue(), 
                    ConfigHistory.OperationType.CREATE, operator, "创建配置");
        
        return saved;
    }
    
    /**
     * 更新配置
     */
    @Transactional
    public SysConfig updateConfig(Long id, SysConfig newConfig, String operator) {
        SysConfig oldConfig = configRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("配置不存在: " + id));
        
        String oldValue = oldConfig.getConfigValue();
        
        // 如果标记为加密，则加密存储
        if (Boolean.TRUE.equals(newConfig.getIsEncrypted()) || newConfig.getDataType() == SysConfig.DataType.ENCRYPTED) {
            newConfig.setConfigValue(encryptionService.encrypt(newConfig.getConfigValue()));
            newConfig.setIsEncrypted(true);
            newConfig.setDataType(SysConfig.DataType.ENCRYPTED);
        }
        
        newConfig.setId(id);
        newConfig.setCreatedBy(oldConfig.getCreatedBy());
        newConfig.setCreatedTime(oldConfig.getCreatedTime());
        newConfig.setUpdatedBy(operator);
        newConfig.setUpdatedTime(LocalDateTime.now());
        newConfig.setIsDeleted(0);
        
        SysConfig saved = configRepository.save(newConfig);
        
        // 记录历史
        saveHistory(saved.getId(), saved.getConfigKey(), oldValue, saved.getConfigValue(), 
                    ConfigHistory.OperationType.UPDATE, operator, "更新配置");
        
        return saved;
    }
    
    /**
     * 回滚配置
     */
    @Transactional
    public SysConfig rollbackConfig(Long configId, Long historyId, String operator) {
        ConfigHistory history = historyRepository.findById(historyId)
                .orElseThrow(() -> new RuntimeException("历史记录不存在: " + historyId));
        
        SysConfig config = configRepository.findById(configId)
                .orElseThrow(() -> new RuntimeException("配置不存在: " + configId));
        
        String oldValue = config.getConfigValue();
        
        // 恢复到历史值
        config.setConfigValue(history.getOldValue());
        config.setUpdatedBy(operator);
        config.setUpdatedTime(LocalDateTime.now());
        
        SysConfig saved = configRepository.save(config);
        
        // 记录回滚历史
        saveHistory(saved.getId(), saved.getConfigKey(), oldValue, saved.getConfigValue(), 
                    ConfigHistory.OperationType.ROLLBACK, operator, "回滚到历史版本: " + historyId);
        
        return saved;
    }
    
    /**
     * 获取配置（含解密）
     */
    public SysConfig getConfig(Long id) {
        SysConfig config = configRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("配置不存在: " + id));
        
        // 如果是加密的，解密返回
        if (Boolean.TRUE.equals(config.getIsEncrypted())) {
            try {
                config.setConfigValue(encryptionService.decrypt(config.getConfigValue()));
            } catch (Exception e) {
                // 解密失败，返回原值
            }
        }
        
        return config;
    }
    
    /**
     * 获取配置（脱敏）
     */
    public SysConfig getConfigMasked(Long id) {
        SysConfig config = getConfig(id);
        
        if (Boolean.TRUE.equals(config.getIsEncrypted())) {
            config.setConfigValue("******");
        }
        
        return config;
    }
    
    /**
     * 获取配置历史
     */
    public List<ConfigHistory> getConfigHistory(Long configId) {
        return historyRepository.findByConfigIdOrderByOperationTimeDesc(configId);
    }
    
    /**
     * 获取所有配置
     */
    public List<SysConfig> getAllConfigs() {
        return configRepository.findByIsDeleted(0);
    }
    
    /**
     * 删除配置（逻辑删除）
     */
    @Transactional
    public void deleteConfig(Long id, String operator) {
        SysConfig config = configRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("配置不存在: " + id));
        
        config.setIsDeleted(1);
        config.setUpdatedBy(operator);
        config.setUpdatedTime(LocalDateTime.now());
        configRepository.save(config);
        
        // 记录历史
        saveHistory(config.getId(), config.getConfigKey(), config.getConfigValue(), null, 
                    ConfigHistory.OperationType.DELETE, operator, "删除配置");
    }
    
    private void saveHistory(Long configId, String configKey, String oldValue, String newValue,
                           ConfigHistory.OperationType operationType, String operator, String remark) {
        ConfigHistory history = new ConfigHistory();
        history.setConfigId(configId);
        history.setConfigKey(configKey);
        history.setOldValue(oldValue);
        history.setNewValue(newValue);
        history.setOperationType(operationType);
        history.setOperator(operator);
        history.setOperationTime(LocalDateTime.now());
        history.setRemark(remark);
        historyRepository.save(history);
    }
}
