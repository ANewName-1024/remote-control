package com.example.config.controller;

import com.example.config.entity.OpenClawConfig;
import com.example.config.security.KeyManagementService;
import com.example.config.service.OpenClawConfigService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * OpenClaw 配置 REST 控制器
 */
@RestController
@RequestMapping("/openclaw")
public class OpenClawConfigController {

    private final OpenClawConfigService configService;
    private final KeyManagementService keyManagementService;

    public OpenClawConfigController(OpenClawConfigService configService,
                                    KeyManagementService keyManagementService) {
        this.configService = configService;
        this.keyManagementService = keyManagementService;
    }

    // ==================== 配置 CRUD ====================

    /**
     * 获取配置
     */
    @GetMapping("/config/{key}")
    public ResponseEntity<?> getConfig(@PathVariable String key) {
        return configService.get(key)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /**
     * 获取配置值（自动解密）
     */
    @GetMapping("/config/{key}/value")
    public ResponseEntity<?> getConfigValue(@PathVariable String key) {
        String value = configService.getValue(key);
        if (value == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of("key", key, "value", value));
    }

    /**
     * 创建/更新配置
     */
    @PostMapping("/config")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> saveConfig(@RequestBody Map<String, Object> request) {
        String key = (String) request.get("key");
        String value = (String) request.get("value");
        String typeStr = (String) request.get("type");
        Boolean encrypt = (Boolean) request.get("encrypt");
        String algorithm = (String) request.get("algorithm");

        OpenClawConfig.ConfigType type = typeStr != null ?
                OpenClawConfig.ConfigType.valueOf(typeStr.toUpperCase()) :
                OpenClawConfig.ConfigType.PARAMETER;

        OpenClawConfig config = configService.save(key, value, type, 
                encrypt != null && encrypt, algorithm);
        
        return ResponseEntity.ok(Map.of(
                "message", "配置保存成功",
                "id", config.getId(),
                "isEncrypted", config.getIsEncrypted()
        ));
    }

    /**
     * 删除配置
     */
    @DeleteMapping("/config/{key}")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> deleteConfig(@PathVariable String key) {
        configService.delete(key);
        return ResponseEntity.ok(Map.of("message", "配置已删除"));
    }

    /**
     * 按类型获取配置
     */
    @GetMapping("/config/type/{type}")
    public ResponseEntity<?> getConfigsByType(@PathVariable String type) {
        OpenClawConfig.ConfigType configType = OpenClawConfig.ConfigType.valueOf(type.toUpperCase());
        List<OpenClawConfig> configs = configService.getByType(configType);
        
        return ResponseEntity.ok(configs.stream().map(c -> Map.of(
                "key", c.getConfigKey(),
                "type", c.getConfigType(),
                "isEncrypted", c.getIsEncrypted()
        )));
    }

    /**
     * 获取所有配置
     */
    @GetMapping("/config/all")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> getAllConfigs() {
        return ResponseEntity.ok(configService.getAllConfigs());
    }

    // ==================== 加密操作 ====================

    /**
     * 加密配置
     */
    @PostMapping("/config/{key}/encrypt")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> encryptConfig(@PathVariable String key,
                                            @RequestBody(required = false) Map<String, String> request) {
        String algorithm = request != null ? request.get("algorithm") : null;
        String encrypted = configService.encryptValue(key, algorithm);
        
        return ResponseEntity.ok(Map.of(
                "key", key,
                "encryptedValue", encrypted,
                "algorithm", algorithm != null ? algorithm : "SM4"
        ));
    }

    /**
     * 解密配置
     */
    @PostMapping("/config/{key}/decrypt")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> decryptConfig(@PathVariable String key) {
        String decrypted = configService.decryptValue(key);
        
        return ResponseEntity.ok(Map.of(
                "key", key,
                "value", decrypted
        ));
    }

    /**
     * 重新加密所有配置
     */
    @PostMapping("/config/reencrypt")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> reEncryptAll(@RequestBody Map<String, String> request) {
        String algorithm = request.get("algorithm");
        configService.reEncryptAll(algorithm != null ? algorithm : "SM4");
        
        return ResponseEntity.ok(Map.of("message", "所有配置已重新加密"));
    }

    // ==================== 密钥管理 ====================

    /**
     * 获取密钥状态
     */
    @GetMapping("/key/status")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> getKeyStatus() {
        return ResponseEntity.ok(keyManagementService.getKeyStatus());
    }

    /**
     * 轮换工作密钥
     */
    @PostMapping("/key/rotate")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> rotateKey() {
        keyManagementService.rotateWorkingKey();
        
        return ResponseEntity.ok(Map.of(
                "message", "工作密钥已轮换",
                "keyId", keyManagementService.getWorkingKeyId()
        ));
    }

    /**
     * 备份根密钥
     */
    @PostMapping("/key/backup")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> backupRootKey(@RequestBody Map<String, String> request) {
        String password = request.get("password");
        
        if (password == null || password.isEmpty()) {
            return ResponseEntity.badRequest().body(Map.of("error", "密码不能为空"));
        }

        String encrypted = keyManagementService.backupRootKey(password);
        
        return ResponseEntity.ok(Map.of(
                "message", "根密钥已备份",
                "encryptedKey", encrypted
        ));
    }

    /**
     * 恢复根密钥
     */
    @PostMapping("/key/restore")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> restoreRootKey(@RequestBody Map<String, String> request) {
        String encryptedKey = request.get("encryptedKey");
        String password = request.get("password");

        if (encryptedKey == null || password == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "参数不完整"));
        }

        try {
            keyManagementService.restoreRootKey(encryptedKey, password);
            return ResponseEntity.ok(Map.of("message", "根密钥已恢复"));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", "恢复失败: " + e.getMessage()));
        }
    }

    // ==================== 初始化 ====================

    /**
     * 初始化默认配置
     */
    @PostMapping("/init")
    @PreAuthorize("hasAuthority('admin:manage')")
    public ResponseEntity<?> initDefaultConfigs() {
        configService.initDefaultConfigs();
        return ResponseEntity.ok(Map.of("message", "默认配置初始化完成"));
    }
}
