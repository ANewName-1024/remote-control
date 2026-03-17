package com.example.config.job;

import com.xxl.job.core.context.XxlJobHelper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.stereotype.Component;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadMXBean;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * 健康检查任务
 * 
 * 使用 XXL-JOB 定时执行系统健康检查
 */
@Component
public class HealthCheckJob {

    private static final Logger logger = LoggerFactory.getLogger(HealthCheckJob.class);

    private static final double MEMORY_THRESHOLD = 0.85;
    private static final double CPU_THRESHOLD = 0.80;

    @Autowired(required = false)
    private BuildProperties buildProperties;

    private final MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
    private final ThreadMXBean threadBean = ManagementFactory.getThreadMXBean();

    /**
     * 健康检查任务
     * Cron: 0 0/5 * * ? (每5分钟)
     */
    @XxlJob("healthCheckJobHandler")
    public void healthCheck() {
        logger.debug("开始执行健康检查任务...");
        
        try {
            Map<String, Object> health = collectHealthInfo();
            
            // 检查内存
            double memoryUsage = (double) health.get("memoryUsage");
            if (memoryUsage > MEMORY_THRESHOLD) {
                logger.warn("内存使用率过高: {:.2f}%", memoryUsage * 100);
                XxlJobHelper.handleFail("内存使用率过高");
                return;
            }
            
            // 检查线程
            int threadCount = (int) health.get("threadCount");
            long peakThreadCount = threadBean.getPeakThreadCount();
            if (threadCount > peakThreadCount * 0.9) {
                logger.warn("线程数接近峰值: {}/{}", threadCount, peakThreadCount);
            }
            
            logger.debug("健康检查完成: {}", health);
            XxlJobHelper.handleSuccess("健康检查完成");
        } catch (Exception e) {
            logger.error("健康检查失败", e);
            XxlJobHelper.handleFail("健康检查失败: " + e.getMessage());
        }
    }

    /**
     * 应用信息记录任务
     * Cron: 0 0 0/1 * * ? (每小时)
     */
    @XxlJob("appInfoLogJobHandler")
    public void appInfoLog() {
        logger.info("========== 应用信息 ==========");
        logger.info("应用名称: {}", buildProperties != null ? buildProperties.getName() : "unknown");
        logger.info("版本: {}", buildProperties != null ? buildProperties.getVersion() : "unknown");
        
        // 记录系统信息
        Runtime runtime = Runtime.getRuntime();
        logger.info("CPU 核心数: {}", runtime.availableProcessors());
        logger.info("最大内存: {} MB", runtime.maxMemory() / 1024 / 1024);
        logger.info("================================");
        
        XxlJobHelper.handleSuccess("应用信息记录完成");
    }

    /**
     * 收集健康信息
     */
    private Map<String, Object> collectHealthInfo() {
        Map<String, Object> health = new HashMap<>();
        
        // 堆内存使用
        long heapUsed = memoryBean.getHeapMemoryUsage().getUsed();
        long heapMax = memoryBean.getHeapMemoryUsage().getMax();
        double memoryUsage = (double) heapUsed / heapMax;
        
        health.put("memoryUsage", memoryUsage);
        health.put("heapUsed", heapUsed);
        health.put("heapMax", heapMax);
        
        // 线程信息
        health.put("threadCount", threadBean.getThreadCount());
        health.put("peakThreadCount", threadBean.getPeakThreadCount());
        
        // 系统负载
        double systemLoad = ManagementFactory.getOperatingSystemMXBean().getSystemLoadAverage();
        health.put("systemLoad", systemLoad);
        
        return health;
    }
}
