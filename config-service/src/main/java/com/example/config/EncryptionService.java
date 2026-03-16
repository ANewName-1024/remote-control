package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.DigestUtils;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.UUID;

@Service
public class EncryptionService {
    
    @Value("${jasypt.encryptor.password:ConfigSecretKey2024}")
    private String secretKey;
    
    // 对称加密算法 AES
    private static final String ALGORITHM = "AES";
    
    /**
     * 加密数据
     */
    public String encrypt(String data) {
        try {
            SecretKey key = new SecretKeySpec(getMD5Key(secretKey), ALGORITHM);
            Cipher cipher = Cipher.getInstance(ALGORITHM);
            cipher.init(Cipher.ENCRYPT_MODE, key);
            byte[] encrypted = cipher.doFinal(data.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(encrypted);
        } catch (Exception e) {
            throw new RuntimeException("加密失败", e);
        }
    }
    
    /**
     * 解密数据
     */
    public String decrypt(String encryptedData) {
        try {
            SecretKey key = new SecretKeySpec(getMD5Key(secretKey), ALGORITHM);
            Cipher cipher = Cipher.getInstance(ALGORITHM);
            cipher.init(Cipher.DECRYPT_MODE, key);
            byte[] decrypted = cipher.doFinal(Base64.getDecoder().decode(encryptedData));
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("解密失败", e);
        }
    }
    
    /**
     * 生成哈希值用于密钥
     */
    private byte[] getMD5Key(String key) {
        return DigestUtils.md5Digest(key.getBytes(StandardCharsets.UTF_8));
    }
    
    /**
     * 生成随机Token
     */
    public String generateToken() {
        return UUID.randomUUID().toString().replace("-", "");
    }
    
    /**
     * 数据脱敏 - 手机号
     */
    public String maskPhone(String phone) {
        if (phone == null || phone.length() < 11) return phone;
        return phone.substring(0, 3) + "****" + phone.substring(7);
    }
    
    /**
     * 数据脱敏 - 身份证号
     */
    public String maskIdCard(String idCard) {
        if (idCard == null || idCard.length() < 8) return idCard;
        return idCard.substring(0, 4) + "**********" + idCard.substring(idCard.length() - 4);
    }
}
