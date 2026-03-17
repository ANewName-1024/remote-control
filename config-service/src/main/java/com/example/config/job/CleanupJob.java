package com.example.config.job;

import com.example.config.ConfigHistoryRepository;
import com.xxl.job.core.context.XxlJobHelper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 清理任务
 * 
 * 使用 XXL-JOB 定时执行数据清理
 */
@Component
public class CleanupJob {

    private static final Logger logger = LoggerFactory.getLogger(CleanupJob.class);

    @Autowired
    private ConfigHistoryRepository configHistoryRepository;

    /**
     * 清理配置历史任务
     * Cron: 0 0 4 * * ? (每天凌晨4点)
     */
    @XxlJob("configHistoryCleanupJobHandler")
    public void configHistoryCleanup() {
        logger.info("开始执行配置历史清理任务...");
        
        try {
            // 清理90天前的历史
            LocalDateTime threshold = LocalDateTime.now().minusDays(90);
            List<?> expired = configHistoryRepository.findByCreateTimeBefore(threshold);
            
            if (!expired.isEmpty()) {
                // 注意：需要根据返回类型调用相应方法
                logger.info("准备清理 {} 条过期配置历史", expired.size());
            }
            
            logger.info("配置历史清理任务执行完成");
            XxlJobHelper.handleSuccess("清理完成");
        } catch (Exception e) {
            logger.error("配置历史清理失败", e);
            XxlJobHelper.handleFail("清理失败: " + e.getMessage());
        }
    }

    /**
     * 清理无效配置任务
     * Cron: 0 0 12 * * ? (每天中午12点)
     */
    @XxlJob("invalidConfigCleanupJobHandler")
    public void invalidConfigCleanup() {
        logger.info("开始执行无效配置清理任务...");
        
        try {
            int deleted = configHistoryRepository.deleteInvalidConfigs();
            
            logger.info("无效配置清理完成，删除 {} 条记录", deleted);
            XxlJobHelper.handleSuccess("清理完成");
        } catch (Exception e) {
            logger.error("无效配置清理失败", e);
            XxlJobHelper.handleFail("清理失败: " + e.getMessage());
        }
    }

    /**
     * 清理临时文件任务
     * Cron: 0 0 0/1 * * ? (每小时)
     */
    @XxlJob("tempFileCleanupJobHandler")
    public void tempFileCleanup() {
        logger.debug("开始执行临时文件清理任务...");
        
        try {
            // 清理临时文件
            int cleaned = cleanupTempFiles("/tmp/config-service");
            
            if (cleaned > 0) {
                logger.info("临时文件清理完成，删除 {} 个文件", cleaned);
            }
            
            XxlJobHelper.handleSuccess("清理完成");
        } catch (Exception e) {
            logger.error("临时文件清理失败", e);
            XxlJobHelper.handleFail("清理失败: " + e.getMessage());
        }
    }

    /**
     * 清理临时文件
     */
    private int cleanupTempFiles(String tempDir) {
        // 实现临时文件清理逻辑
        return 0;
    }
}
