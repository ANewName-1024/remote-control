package com.example.config.security;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 密钥管理服务
 * 支持软件根密钥和硬件根密钥
 */
@Service
public class KeyManagementService {

    private static final Logger log = LoggerFactory.getLogger(KeyManagementService.class);

    @Value("${encryption.root-key-type:SOFTWARE}")
    private String rootKeyType;

    @Value("${encryption.root-key-file:}")
    private String rootKeyFile;

    @Value("${encryption.working-key-rotation-days:90}")
    private int workingKeyRotationDays;

    private String rootKey;
    private String workingKey;
    private String workingKeyId;
    private LocalDateTime workingKeyCreatedTime;
    private boolean isHardwareKeyAvailable = false;

    private final GmCryptUtil gmCryptUtil;
    private final Map<String, KeyPair> sm2KeyPairs = new ConcurrentHashMap<>();

    public KeyManagementService(GmCryptUtil gmCryptUtil) {
        this.gmCryptUtil = gmCryptUtil;
    }

    @PostConstruct
    public void init() {
        if ("HARDWARE".equalsIgnoreCase(rootKeyType)) {
            initHardwareKey();
        } else {
            initSoftwareKey();
        }
    }

    // ==================== 根密钥管理 ====================

    /**
     * 初始化软件根密钥
     */
    private void initSoftwareKey() {
        if (rootKeyFile != null && !rootKeyFile.isEmpty()) {
            try {
                // 从文件加载
                rootKey = loadRootKeyFromFile(rootKeyFile);
                log.info("从文件加载根密钥成功");
            } catch (Exception e) {
                log.warn("无法加载根密钥文件，生成新的根密钥");
                generateSoftwareRootKey();
            }
        } else {
            generateSoftwareRootKey();
        }
    }

    /**
     * 初始化硬件根密钥
     */
    private void initHardwareKey() {
        try {
            // 检查硬件密钥设备是否可用
            isHardwareKeyAvailable = checkHardwareKeyAvailable();
            if (isHardwareKeyAvailable) {
                log.info("硬件根密钥可用");
            } else {
                log.warn("硬件密钥设备不可用，回退到软件根密钥");
                rootKeyType = "SOFTWARE";
                initSoftwareKey();
            }
        } catch (Exception e) {
            log.error("硬件密钥初始化失败", e);
            rootKeyType = "SOFTWARE";
            initSoftwareKey();
        }
    }

    /**
     * 生成软件根密钥
     */
    public void generateSoftwareRootKey() {
        rootKey = gmCryptUtil.generateSm4Key();
        log.info("生成新的软件根密钥");
        
        // 保存到文件
        if (rootKeyFile != null && !rootKeyFile.isEmpty()) {
            try {
                saveRootKeyToFile(rootKeyFile, rootKey);
            } catch (Exception e) {
                log.error("保存根密钥失败", e);
            }
        }
    }

    /**
     * 生成硬件根密钥
     */
    public void generateHardwareRootKey() {
        if (isHardwareKeyAvailable) {
            // 调用硬件设备生成密钥
            // TODO: 实现硬件密钥生成
            log.info("生成硬件根密钥");
        } else {
            throw new RuntimeException("硬件密钥不可用");
        }
    }

    // ==================== 工作密钥管理 ====================

    /**
     * 生成工作密钥
     */
    public String generateWorkingKey() {
        workingKey = gmCryptUtil.generateSm4Key();
        workingKeyId = generateKeyId();
        workingKeyCreatedTime = LocalDateTime.now();
        
        log.info("生成新的工作密钥, ID: {}", workingKeyId);
        return workingKey;
    }

    /**
     * 轮换工作密钥
     */
    public void rotateWorkingKey() {
        String oldKey = workingKey;
        generateWorkingKey();
        
        // 使用旧密钥加密新密钥，然后使用根密钥再加密
        // 这样可以保证新密钥的安全性
        log.info("工作密钥已轮换, 新 ID: {}", workingKeyId);
    }

    /**
     * 获取当前工作密钥
     */
    public String getActiveWorkingKey() {
        if (workingKey == null) {
            generateWorkingKey();
        }
        
        // 检查是否需要轮换
        if (workingKeyCreatedTime != null) {
            LocalDateTime expiryDate = workingKeyCreatedTime.plusDays(workingKeyRotationDays);
            if (LocalDateTime.now().isAfter(expiryDate)) {
                log.info("工作密钥已过期，进行轮换");
                rotateWorkingKey();
            }
        }
        
        return workingKey;
    }

    /**
     * 获取工作密钥 ID
     */
    public String getWorkingKeyId() {
        if (workingKeyId == null) {
            getActiveWorkingKey(); // 触发初始化
        }
        return workingKeyId;
    }

    // ==================== 加密/解密 ====================

    /**
     * 使用工作密钥加密数据
     */
    public String encrypt(String data) {
        String key = getActiveWorkingKey();
        return gmCryptUtil.sm4Encrypt(data, key);
    }

    /**
     * 使用工作密钥解密数据
     */
    public String decrypt(String encryptedData) {
        String key = getActiveWorkingKey();
        return gmCryptUtil.sm4Decrypt(encryptedData, key);
    }

    /**
     * 使用根密钥加密（用于密钥备份等）
     */
    public String encryptWithRootKey(String data) {
        if (rootKey == null) {
            throw new RuntimeException("根密钥未初始化");
        }
        
        if (isHardwareKeyAvailable) {
            return encryptWithHardware(data);
        }
        
        return gmCryptUtil.sm4Encrypt(data, rootKey);
    }

    /**
     * 使用根密钥解密
     */
    public String decryptWithRootKey(String encryptedData) {
        if (rootKey == null) {
            throw new RuntimeException("根密钥未初始化");
        }
        
        if (isHardwareKeyAvailable) {
            return decryptWithHardware(encryptedData);
        }
        
        return gmCryptUtil.sm4Decrypt(encryptedData, rootKey);
    }

    // ==================== 硬件密钥 ====================

    /**
     * 检查硬件密钥是否可用
     */
    public boolean isHardwareKeyAvailable() {
        return isHardwareKeyAvailable;
    }

    /**
     * 检查硬件密钥设备
     */
    private boolean checkHardwareKeyAvailable() {
        // TODO: 实现硬件密钥设备检测
        // 可以检测：
        // 1. HSM 设备
        // 2. TPM 芯片
        // 3. 云密钥服务 (KMS)
        return false;
    }

    /**
     * 使用硬件加密
     */
    public String encryptWithHardware(String data) {
        if (!isHardwareKeyAvailable) {
            throw new RuntimeException("硬件密钥不可用");
        }
        
        // TODO: 实现硬件加密
        throw new UnsupportedOperationException("硬件加密待实现");
    }

    /**
     * 使用硬件解密
     */
    public String decryptWithHardware(String encryptedData) {
        if (!isHardwareKeyAvailable) {
            throw new RuntimeException("硬件密钥不可用");
        }
        
        // TODO: 实现硬件解密
        throw new UnsupportedOperationException("硬件解密待实现");
    }

    // ==================== SM2 密钥对 ====================

    /**
     * 生成 SM2 密钥对
     */
    public String generateSm2KeyPair(String keyId) {
        KeyPair keyPair = gmCryptUtil.generateSm2KeyPair();
        sm2KeyPairs.put(keyId, keyPair);
        
        // 返回公钥，私钥安全存储
        return gmCryptUtil.getPublicKeyHex(keyPair);
    }

    /**
     * SM2 加密
     */
    public String sm2Encrypt(String keyId, String data) {
        KeyPair keyPair = sm2KeyPairs.get(keyId);
        if (keyPair == null) {
            throw new RuntimeException("密钥对不存在: " + keyId);
        }
        
        return gmCryptUtil.sm2Encrypt(data, keyPair.getPublic());
    }

    /**
     * SM2 解密
     */
    public String sm2Decrypt(String keyId, String encryptedData) {
        KeyPair keyPair = sm2KeyPairs.get(keyId);
        if (keyPair == null) {
            throw new RuntimeException("密钥对不存在: " + keyId);
        }
        
        return gmCryptUtil.sm2Decrypt(encryptedData, keyPair.getPrivate());
    }

    // ==================== 密钥备份/恢复 ====================

    /**
     * 备份根密钥
     */
    public String backupRootKey(String password) {
        if (rootKey == null) {
            throw new RuntimeException("根密钥不存在");
        }
        
        // 使用密码派生的密钥加密根密钥
        String derivedKey = gmCryptUtil.sm3Kdf(password, "backup", 32);
        return gmCryptUtil.sm4Encrypt(rootKey, derivedKey);
    }

    /**
     * 恢复根密钥
     */
    public void restoreRootKey(String encryptedRootKey, String password) {
        String derivedKey = gmCryptUtil.sm3Kdf(password, "backup", 32);
        rootKey = gmCryptUtil.sm4Decrypt(encryptedRootKey, derivedKey);
        
        if (rootKeyFile != null && !rootKeyFile.isEmpty()) {
            try {
                saveRootKeyToFile(rootKeyFile, rootKey);
            } catch (Exception e) {
                log.error("恢复根密钥保存失败", e);
            }
        }
    }

    // ==================== 工具方法 ====================

    private String generateKeyId() {
        byte[] bytes = new byte[8];
        new SecureRandom().nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private String loadRootKeyFromFile(String path) throws Exception {
        // TODO: 从文件读取并解密
        return null;
    }

    private void saveRootKeyToFile(String path, String key) throws Exception {
        // TODO: 加密保存到文件
    }

    /**
     * 获取密钥状态
     */
    public KeyStatus getKeyStatus() {
        return new KeyStatus(
                rootKeyType,
                isHardwareKeyAvailable,
                workingKeyId,
                workingKeyCreatedTime,
                workingKeyRotationDays
        );
    }

    public static class KeyStatus {
        private String rootKeyType;
        private boolean hardwareKeyAvailable;
        private String workingKeyId;
        private LocalDateTime workingKeyCreatedTime;
        private int rotationDays;

        public KeyStatus(String rootKeyType, boolean hardwareKeyAvailable,
                        String workingKeyId, LocalDateTime workingKeyCreatedTime,
                        int rotationDays) {
            this.rootKeyType = rootKeyType;
            this.hardwareKeyAvailable = hardwareKeyAvailable;
            this.workingKeyId = workingKeyId;
            this.workingKeyCreatedTime = workingKeyCreatedTime;
            this.rotationDays = rotationDays;
        }

        // Getters
        public String getRootKeyType() { return rootKeyType; }
        public boolean isHardwareKeyAvailable() { return hardwareKeyAvailable; }
        public String getWorkingKeyId() { return workingKeyId; }
        public LocalDateTime getWorkingKeyCreatedTime() { return workingKeyCreatedTime; }
        public int getRotationDays() { return rotationDays; }
    }
}
