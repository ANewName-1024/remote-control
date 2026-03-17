package com.example.config.service;

import com.example.config.entity.OpenClawConfig;
import com.example.config.repository.OpenClawConfigRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;

/**
 * OpenClaw 配置服务
 */
@Service
public class OpenClawConfigService {

    private static final Logger log = LoggerFactory.getLogger(OpenClawConfigService.class);

    private final OpenClawConfigRepository repository;

    public OpenClawConfigService(OpenClawConfigRepository repository) {
        this.repository = repository;
    }

    // ==================== 配置 CRUD ====================

    /**
     * 保存配置
     */
    @Transactional
    public OpenClawConfig save(String key, String value, String configType) {
        Optional<OpenClawConfig> existing = repository.findByConfigKey(key);
        
        OpenClawConfig config;
        if (existing.isPresent()) {
            config = existing.get();
        } else {
            config = new OpenClawConfig();
            config.setConfigKey(key);
            config.setCreatedTime(LocalDateTime.now());
        }

        config.setConfigValue(value);
        config.setConfigType(configType);
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
     * 获取配置值
     */
    public String getValue(String key) {
        Optional<OpenClawConfig> config = repository.findByConfigKey(key);
        return config.map(OpenClawConfig::getConfigValue).orElse(null);
    }

    /**
     * 获取所有配置
     */
    public Map<String, String> getAllConfigs() {
        List<OpenClawConfig> configs = repository.findAll();
        Map<String, String> result = new HashMap<>();
        for (OpenClawConfig config : configs) {
            result.put(config.getConfigKey(), config.getConfigValue());
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

    /**
     * 初始化默认配置
     */
    public void initDefaultConfigs() {
        save("gateway.enabled", "true", "GATEWAY");
        save("gateway.port", "8080", "GATEWAY");
        save("extension.feishu.enabled", "false", "EXTENSION");
        save("extension.telegram.enabled", "false", "EXTENSION");
        save("skill.weather.enabled", "true", "SKILL");
        save("skill.github.enabled", "false", "SKILL");
        save("memory.daily.enabled", "true", "MEMORY");
        save("memory.longterm.enabled", "true", "MEMORY");
        log.info("OpenClaw 默认配置初始化完成");
    }
}
