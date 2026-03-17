package com.example.config.job;

import com.example.config.EncryptionService;
import com.xxl.job.core.context.XxlJobHelper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * 密钥轮换任务
 * 
 * 使用 XXL-JOB 定时执行密钥轮换
 */
@Component
public class KeyRotationJob {

    private static final Logger logger = LoggerFactory.getLogger(KeyRotationJob.class);

    @Autowired
    private EncryptionService encryptionService;

    /**
     * 密钥轮换任务
     * Cron: 0 0 2 * * ? (每天凌晨2点)
     */
    @XxlJob("keyRotationJobHandler")
    public void keyRotation() {
        logger.info("开始执行密钥轮换任务...");
        
        try {
            encryptionService.rotateDataKey();
            
            logger.info("密钥轮换任务执行完成，时间: {}", LocalDateTime.now());
            XxlJobHelper.handleSuccess("密钥轮换成功");
        } catch (Exception e) {
            logger.error("密钥轮换任务执行失败", e);
            XxlJobHelper.handleFail("密钥轮换失败: " + e.getMessage());
        }
    }

    /**
     * 密钥健康检查任务
     * Cron: 0 0 0/1 * * ? (每小时)
     */
    @XxlJob("keyHealthCheckJobHandler")
    public void keyHealthCheck() {
        logger.debug("开始执行密钥健康检查...");
        
        try {
            Map<String, Object> health = encryptionService.checkKeyHealth();
            
            int expiringKeys = (int) health.getOrDefault("expiringKeys", 0);
            
            if (expiringKeys > 0) {
                logger.warn("发现 {} 个即将过期的密钥", expiringKeys);
                XxlJobHelper.handleSuccess("发现 " + expiringKeys + " 个即将过期的密钥");
            } else {
                logger.debug("密钥健康检查完成，无异常");
                XxlJobHelper.handleSuccess("密钥健康");
            }
        } catch (Exception e) {
            logger.error("密钥健康检查失败", e);
            XxlJobHelper.handleFail("密钥健康检查失败: " + e.getMessage());
        }
    }

    /**
     * 密钥备份任务
     * Cron: 0 0 3 ? * SUN (每周日凌晨3点)
     */
    @XxlJob("keyBackupJobHandler")
    public void keyBackup() {
        logger.info("开始执行密钥备份任务...");
        
        try {
            encryptionService.backupKeys();
            
            logger.info("密钥备份完成");
            XxlJobHelper.handleSuccess("密钥备份成功");
        } catch (Exception e) {
            logger.error("密钥备份失败", e);
            XxlJobHelper.handleFail("密钥备份失败: " + e.getMessage());
        }
    }

    /**
     * 密钥版本清理任务
     * Cron: 0 0 4 1 * ? (每月1号凌晨4点)
     */
    @XxlJob("keyCleanupJobHandler")
    public void keyCleanup() {
        logger.info("开始执行密钥版本清理任务...");
        
        try {
            // 保留最近3个版本
            int deleted = encryptionService.cleanOldKeyVersions(3);
            
            logger.info("密钥版本清理完成，删除 {} 个旧版本", deleted);
            XxlJobHelper.handleSuccess("清理完成");
        } catch (Exception e) {
            logger.error("密钥版本清理失败", e);
            XxlJobHelper.handleFail("清理失败: " + e.getMessage());
        }
    }
}
