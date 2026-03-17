package com.example.config.job;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import com.xxl.job.core.executor.XxlJobExecutor;
import com.xxl.job.core.executor.impl.XxlJobSpringExecutor;

/**
 * XXL-Job 配置
 * 
 * 使用 XXL-JOB 替代 Spring @Scheduled
 * 
 * 配置说明：
 * - xxl.job.admin.addresses: 调度中心地址
 * - xxl.job.executor.appname: 执行器名称
 * - xxl.job.executor.port: 执行器端口
 */
@Configuration
@ConditionalOnProperty(name = "xxl.job.enabled", havingValue = "true", matchIfMissing = false)
public class XxlJobConfig {

    private static final Logger logger = LoggerFactory.getLogger(XxlJobConfig.class);

    @Value("${xxl.job.admin.addresses:http://127.0.0.1:8080/xxl-job-admin}")
    private String adminAddresses;

    @Value("${xxl.job.accessToken:default_token}")
    private String accessToken;

    @Value("${xxl.job.executor.appname:config-service}")
    private String appname;

    @Value("${xxl.job.executor.port:9999}")
    private int port;

    @Value("${xxl.job.executor.logpath:./logs/xxl-job}")
    private String logPath;

    @Value("${xxl.job.executor.logretentiondays:30}")
    private int logRetentionDays;

    @Bean
    public XxlJobSpringExecutor xxlJobExecutor() {
        logger.info("========== XXL-JOB 配置初始化 ==========");
        logger.info("调度中心地址: {}", adminAddresses);
        logger.info("执行器名称: {}", appname);
        logger.info("执行器端口: {}", port);

        XxlJobSpringExecutor xxlJobSpringExecutor = new XxlJobSpringExecutor();
        xxlJobSpringExecutor.setAdminAddresses(adminAddresses);
        xxlJobSpringExecutor.setAppname(appname);
        xxlJobSpringExecutor.setPort(port);
        xxlJobSpringExecutor.setAccessToken(accessToken);
        xxlJobSpringExecutor.setLogPath(logPath);
        xxlJobSpringExecutor.setLogRetentionDays(logRetentionDays);

        return xxlJobSpringExecutor;
    }
}
