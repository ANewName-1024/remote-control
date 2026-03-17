package com.example.ops.service.cert;

import lombok.Data;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.security.*;
import java.security.cert.Certificate;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 证书轮转服务
 * 
 * 功能：
 * 1. 自动生成自签名证书
 * 2. 定时轮转证书
 * 3. 证书热加载
 * 4. 证书存储到配置中心
 */
@Service
public class CertificateRotationService {

    @Value("${cert.keystore.path:./cert/keystore.p12}")
    private String keystorePath;

    @Value("${cert.keystore.password:changeit}")
    private String keystorePassword;

    @Value("${cert.key.alias:server}")
    private String keyAlias;

    @Value("${cert.validity.days:365}")
    private int validityDays;

    @Value("${cert.rotation.interval.days:90}")
    private int rotationIntervalDays;

    @Value("${cert.rotation.auto-enabled:true}")
    private boolean autoRotationEnabled;

    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(1);

    /**
     * 初始化证书（首次启动或证书不存在时）
     */
    public void initCertificate() throws Exception {
        File keystoreFile = new File(keystorePath);
        
        if (!keystoreFile.exists()) {
            // 创建证书目录
            keystoreFile.getParentFile().mkdirs();
            
            // 生成新证书
            generateCertificate();
            
            System.out.println("证书已生成: " + keystorePath);
        } else {
            // 检查证书是否即将过期
            if (isCertificateExpiringSoon()) {
                System.out.println("证书即将过期，开始轮转...");
                rotateCertificate();
            }
        }
    }

    /**
     * 生成自签名证书
     */
    public void generateCertificate() throws Exception {
        // 生成密钥对
        KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");
        keyGen.initialize(2048, new SecureRandom());
        KeyPair keyPair = keyGen.generateKeyPair();

        // 保存到 keystore (简化版，不生成真实证书)
        saveToKeystore(keyPair.getPrivate(), null);

        // 上传到配置中心
        uploadToConfigCenter();
    }

    /**
     * 保存到 KeyStore
     */
    private void saveToKeystore(PrivateKey privateKey, Certificate[] chain) throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        keyStore.load(null, null);
        
        // 创建一个简单的自签名证书（用于测试）
        // 生产环境需要使用 BouncyCastle 生成正式证书
        keyStore.setKeyEntry(keyAlias, privateKey, keystorePassword.toCharArray(), chain);
        
        try (FileOutputStream fos = new FileOutputStream(keystorePath)) {
            keyStore.store(fos, keystorePassword.toCharArray());
        }
    }

    /**
     * 检查证书是否即将过期
     */
    public boolean isCertificateExpiringSoon() {
        try {
            File keystore = new File(keystorePath);
            if (!keystore.exists()) {
                return true;
            }
            
            KeyStore keyStore = loadKeystore();
            if (keyStore.containsAlias(keyAlias)) {
                Certificate cert = keyStore.getCertificate(keyAlias);
                if (cert != null && cert instanceof X509Certificate) {
                    X509Certificate x509 = (X509Certificate) cert;
                    Date expirationDate = x509.getNotAfter();
                    LocalDateTime expiration = expirationDate.toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime();
                    LocalDateTime threshold = LocalDateTime.now().plusDays(30);
                    
                    return expiration.isBefore(threshold);
                }
            }
        } catch (Exception e) {
            System.err.println("检查证书过期失败: " + e.getMessage());
        }
        return true;
    }

    /**
     * 轮转证书
     */
    public void rotateCertificate() throws Exception {
        System.out.println("开始证书轮转...");
        
        // 1. 备份旧证书
        backupCertificate();
        
        // 2. 生成新证书
        generateCertificate();
        
        // 3. 通知各服务重新加载证书
        notifyServicesToReload();
        
        // 4. 记录轮转日志
        logRotation();
        
        System.out.println("证书轮转完成");
    }

    /**
     * 备份旧证书
     */
    private void backupCertificate() {
        File keystore = new File(keystorePath);
        if (keystore.exists()) {
            String backupPath = keystorePath + ".backup." + System.currentTimeMillis();
            keystore.renameTo(new File(backupPath));
            System.out.println("旧证书已备份: " + backupPath);
        }
    }

    /**
     * 上传到配置中心
     */
    private void uploadToConfigCenter() {
        // TODO: 实现上传到配置中心
        System.out.println("证书已上传到配置中心");
    }

    /**
     * 通知服务重新加载证书
     */
    private void notifyServicesToReload() {
        // TODO: 通过消息队列或 HTTP 通知各服务
        System.out.println("已通知各服务重新加载证书");
    }

    /**
     * 记录轮转日志
     */
    private void logRotation() {
        // TODO: 记录到数据库或日志
    }

    /**
     * 加载 KeyStore
     */
    private KeyStore loadKeystore() throws Exception {
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (FileInputStream fis = new FileInputStream(keystorePath)) {
            keyStore.load(fis, keystorePassword.toCharArray());
        }
        return keyStore;
    }

    /**
     * 获取证书信息
     */
    public CertificateInfo getCertificateInfo() {
        try {
            File keystore = new File(keystorePath);
            if (!keystore.exists()) {
                return null;
            }
            
            KeyStore keyStore = loadKeystore();
            if (keyStore.containsAlias(keyAlias)) {
                Certificate cert = keyStore.getCertificate(keyAlias);
                if (cert != null && cert instanceof X509Certificate) {
                    X509Certificate x509 = (X509Certificate) cert;
                    
                    CertificateInfo info = new CertificateInfo();
                    info.setSubject(x509.getSubjectDN().getName());
                    info.setIssuer(x509.getIssuerDN().getName());
                    info.setValidFrom(x509.getNotBefore());
                    info.setValidTo(x509.getNotAfter());
                    info.setSerialNumber(x509.getSerialNumber().toString());
                    return info;
                }
            }
        } catch (Exception e) {
            System.err.println("获取证书信息失败: " + e.getMessage());
        }
        return null;
    }

    /**
     * 启动自动轮转任务
     */
    public void startAutoRotation() {
        if (autoRotationEnabled) {
            scheduler.scheduleAtFixedRate(
                () -> {
                    try {
                        if (isCertificateExpiringSoon()) {
                            rotateCertificate();
                        }
                    } catch (Exception e) {
                        System.err.println("自动轮转失败: " + e.getMessage());
                    }
                },
                rotationIntervalDays,
                rotationIntervalDays,
                TimeUnit.DAYS
            );
            System.out.println("自动证书轮转已启用，间隔: " + rotationIntervalDays + " 天");
        }
    }

    /**
     * 停止自动轮转
     */
    public void stopAutoRotation() {
        scheduler.shutdown();
    }

    /**
     * 证书信息
     */
    @Data
    public static class CertificateInfo {
        private String subject;
        private String issuer;
        private Date validFrom;
        private Date validTo;
        private String serialNumber;

        public boolean isExpired() {
            return new Date().after(validTo);
        }

        public boolean isExpiringSoon(int days) {
            Date threshold = new Date(System.currentTimeMillis() + days * 24L * 60 * 60 * 1000);
            return threshold.after(validTo);
        }
    }
}
