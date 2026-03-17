package com.example.config.security;

import org.bouncycastle.crypto.InvalidCipherTextException;
import org.bouncycastle.crypto.engines.SM4Engine;
import org.bouncycastle.crypto.modes.CBCBlockCipher;
import org.bouncycastle.crypto.paddings.PaddedBufferedBlockCipher;
import org.bouncycastle.crypto.params.KeyParameter;
import org.bouncycastle.crypto.params.ParametersWithIV;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jce.spec.SM2ParameterSpec;
import org.bouncycastle.jce.spec.SM2PublicKeySpec;
import org.bouncycastle.math.ec.ECPoint;
import org.bouncycastle.util.encoders.Hex;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.ECGenParameterSpec;
import java.util.Base64;

/**
 * 国密算法工具类
 * 支持 SM2/SM3/SM4
 */
@Component
public class GmCryptUtil {

    static {
        Security.addProvider(new BouncyCastleProvider());
    }

    private static final String SM4_ALGORITHM = "SM4";
    private static final String SM3_ALGORITHM = "SM3";
    private static final String SM2_CURVE = "sm2p256v1";

    // ==================== SM4 对称加密 ====================

    /**
     * SM4 加密 (CBC 模式)
     */
    public String sm4Encrypt(String data, String key) {
        try {
            byte[] keyBytes = hexToBytes(key);
            byte[] iv = new byte[16]; // 16字节零 IV

            PaddedBufferedBlockCipher cipher = new PaddedBufferedBlockCipher(
                    new CBCBlockCipher(new SM4Engine()));
            KeyParameter keyParam = new KeyParameter(keyBytes);
            ParametersWithIV params = new ParametersWithIV(keyParam, iv);
            cipher.init(true, params);

            byte[] input = data.getBytes(StandardCharsets.UTF_8);
            byte[] output = new byte[cipher.getOutputSize(input)];
            int length = cipher.processBytes(input, 0, input.length, output, 0);
            length += cipher.doFinal(output, length);

            byte[] result = new byte[length];
            System.arraycopy(output, 0, result, 0, length);
            return Base64.getEncoder().encodeToString(result);
        } catch (Exception e) {
            throw new RuntimeException("SM4 加密失败", e);
        }
    }

    /**
     * SM4 解密 (CBC 模式)
     */
    public String sm4Decrypt(String encryptedData, String key) {
        try {
            byte[] keyBytes = hexToBytes(key);
            byte[] iv = new byte[16];
            byte[] encrypted = Base64.getDecoder().decode(encryptedData);

            PaddedBufferedBlockCipher cipher = new PaddedBufferedBlockCipher(
                    new CBCBlockCipher(new SM4Engine()));
            KeyParameter keyParam = new KeyParameter(keyBytes);
            ParametersWithIV params = new ParametersWithIV(keyParam, iv);
            cipher.init(false, params);

            byte[] output = new byte[cipher.getOutputSize(encrypted.length)];
            int length = cipher.processBytes(encrypted, 0, encrypted.length, output, 0);
            length += cipher.doFinal(output, length);

            byte[] result = new byte[length];
            System.arraycopy(output, 0, result, 0, length);
            return new String(result, StandardCharsets.UTF_8).trim();
        } catch (Exception e) {
            throw new RuntimeException("SM4 解密失败", e);
        }
    }

    /**
     * 生成 SM4 随机密钥 (128位)
     */
    public String generateSm4Key() {
        byte[] key = new byte[16];
        new SecureRandom().nextBytes(key);
        return bytesToHex(key);
    }

    // ==================== SM3 摘要 ====================

    /**
     * SM3 摘要
     */
    public String sm3Digest(String data) {
        try {
            MessageDigest digest = MessageDigest.getInstance(SM3_ALGORITHM, "BC");
            byte[] hash = digest.digest(data.getBytes(StandardCharsets.UTF_8));
            return bytesToHex(hash);
        } catch (Exception e) {
            throw new RuntimeException("SM3 摘要计算失败", e);
        }
    }

    /**
     * SM3 验证
     */
    public boolean sm3Verify(String data, String expectedDigest) {
        String actualDigest = sm3Digest(data);
        return actualDigest.equalsIgnoreCase(expectedDigest);
    }

    /**
     * SM3 密钥派生 (KDF)
     */
    public String sm3Kdf(String password, String salt, int keyLength) {
        String combined = password + salt;
        StringBuilder key = new StringBuilder();
        int counter = 1;

        while (key.length() < keyLength) {
            String hash = sm3Digest(combined + counter);
            key.append(hash);
            counter++;
        }

        return key.substring(0, keyLength);
    }

    // ==================== SM2 非对称加密 ====================

    /**
     * 生成 SM2 密钥对
     */
    public KeyPair generateSm2KeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("EC", "BC");
            generator.initialize(new ECGenParameterSpec(SM2_CURVE), new SecureRandom());
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new RuntimeException("SM2 密钥对生成失败", e);
        }
    }

    /**
     * SM2 公钥加密
     */
    public String sm2Encrypt(String data, PublicKey publicKey) {
        try {
            SM2ParameterSpec spec = new SM2ParameterSpec(
                    Hex.decode("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF"));
            Cipher cipher = Cipher.getInstance("SM2", "BC");
            cipher.init(Cipher.ENCRYPT_MODE, publicKey, spec);
            byte[] encrypted = cipher.doFinal(data.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(encrypted);
        } catch (Exception e) {
            throw new RuntimeException("SM2 加密失败", e);
        }
    }

    /**
     * SM2 私钥解密
     */
    public String sm2Decrypt(String encryptedData, PrivateKey privateKey) {
        try {
            byte[] encrypted = Base64.getDecoder().decode(encryptedData);
            SM2ParameterSpec spec = new SM2ParameterSpec(
                    Hex.decode("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF"));
            Cipher cipher = Cipher.getInstance("SM2", "BC");
            cipher.init(Cipher.DECRYPT_MODE, privateKey, spec);
            byte[] decrypted = cipher.doFinal(encrypted);
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("SM2 解密失败", e);
        }
    }

    /**
     * 获取公钥 hex 字符串
     */
    public String getPublicKeyHex(KeyPair keyPair) {
        ECPoint point = (ECPoint) keyPair.getPublic().getEncoded();
        return bytesToHex(point.getEncoded(false));
    }

    /**
     * 获取私钥 hex 字符串
     */
    public String getPrivateKeyHex(KeyPair keyPair) {
        return bytesToHex(keyPair.getPrivate().getEncoded());
    }

    // ==================== 工具方法 ====================

    private byte[] hexToBytes(String hex) {
        return Hex.decode(hex);
    }

    private String bytesToHex(byte[] bytes) {
        return Hex.toHexString(bytes);
    }

    /**
     * 从 hex 字符串恢复公钥
     */
    public PublicKey恢复PublicKeyFromHex(String hex) throws Exception {
        byte[] publicKeyBytes = Hex.decode(hex);
        // 需要使用 BouncyCastle 的 API 恢复
        // 这里返回简化实现
        return null;
    }

    /**
     * 从 hex 字符串恢复私钥
     */
    public PrivateKey恢复PrivateKeyFromHex(String hex) throws Exception {
        byte[] privateKeyBytes = Hex.decode(hex);
        // 需要使用 BouncyCastle 的 API 恢复
        // 这里返回简化实现
        return null;
    }
}
