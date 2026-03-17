package com.example.config.job;

import com.example.config.ConfigHistoryRepository;
import com.example.config.ConfigService;
import com.example.config.EncryptionService;
import com.xxl.job.core.context.XxlJobHelper;
import com.xxl.job.core.handler.annotation.XxlJob;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * 配置刷新任务
 * 
 * 使用 XXL-JOB 定时执行配置刷新
 */
@Component
public class ConfigRefreshJob {

    private static final Logger logger = LoggerFactory.getLogger(ConfigRefreshJob.class);

    @Autowired
    private ConfigService configService;

    @Autowired
    private EncryptionService encryptionService;

    /**
     * 配置刷新任务
     * Cron: 0 0/5 * * ? (每5分钟)
     */
    @XxlJob("configRefreshJobHandler")
    public void configRefresh() {
        logger.info("开始执行配置刷新任务...");
        
        try {
            // 1. 刷新配置缓存
            configService.refreshConfigCache();
            
            // 2. 验证加密密钥
            encryptionService.verifyMasterKey();
            
            logger.info("配置刷新任务执行完成");
            XxlJobHelper.handleSuccess("配置刷新成功");
        } catch (Exception e) {
            logger.error("配置刷新任务执行失败", e);
            XxlJobHelper.handleFail("配置刷新失败: " + e.getMessage());
        }
    }

    /**
     * Git 配置变更检测任务
     * Cron: 0 0/1 * * ? (每1分钟)
     */
    @XxlJob("configChangeDetectJobHandler")
    public void configChangeDetect() {
        logger.debug("检测配置变更...");
        
        try {
            boolean hasChanges = configService.checkGitConfigChanges();
            
            if (hasChanges) {
                logger.info("检测到配置变更，触发刷新...");
                configService.refreshConfigCache();
                XxlJobHelper.handleSuccess("检测到配置变更并刷新");
            } else {
                XxlJobHelper.handleSuccess("无配置变更");
            }
        } catch (Exception e) {
            logger.error("配置变更检测失败", e);
            XxlJobHelper.handleFail("检测失败: " + e.getMessage());
        }
    }

    /**
     * 配置同步任务
     * Cron: 0 0/10 * * ? (每10分钟)
     */
    @XxlJob("configSyncJobHandler")
    public void configSync() {
        logger.info("开始执行配置同步任务...");
        
        try {
            Map<String, String> services = configService.getRegisteredServices();
            
            int success = 0;
            int failed = 0;
            
            for (Map.Entry<String, String> entry : services.entrySet()) {
                String serviceName = entry.getKey();
                String serviceUrl = entry.getValue();
                
                boolean result = configService.pushConfigToService(serviceName, serviceUrl);
                
                if (result) {
                    success++;
                } else {
                    failed++;
                    logger.warn("配置同步失败: {}", serviceName);
                }
            }
            
            logger.info("配置同步完成: 成功 {}, 失败 {}", success, failed);
            
            if (failed > 0) {
                XxlJobHelper.handleFail("部分服务同步失败");
            } else {
                XxlJobHelper.handleSuccess("配置同步成功");
            }
        } catch (Exception e) {
            logger.error("配置同步任务执行失败", e);
            XxlJobHelper.handleFail("配置同步失败: " + e.getMessage());
        }
    }
}
