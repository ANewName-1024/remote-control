package com.example.config.scheduler;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;

/**
 * 定时任务配置属性
 * 
 * 支持通过配置文件或配置中心动态管理定时任务
 */
@Configuration
@ConfigurationProperties(prefix = "scheduler.tasks")
public class SchedulerProperties {

    private static final Logger logger = LoggerFactory.getLogger(SchedulerProperties.class);

    /**
     * 是否启用所有定时任务
     */
    private boolean enabled = true;

    /**
     * 任务配置 Map
     */
    private Map<String, TaskProperties> tasks = new HashMap<>();

    // Getters and Setters

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
        logger.info("定时任务全局开关: {}", enabled ? "启用" : "禁用");
    }

    public Map<String, TaskProperties> getTasks() {
        return tasks;
    }

    public void setTasks(Map<String, TaskProperties> tasks) {
        this.tasks = tasks;
        
        // 打印任务配置
        tasks.forEach((name, task) -> {
            logger.info("定时任务配置: {} - enabled:{}, cron: {}, rate: {}ms", 
                    name, task.isEnabled(), task.getCron(), task.getRate());
        });
    }

    /**
     * 检查任务是否启用
     */
    public boolean isTaskEnabled(String taskName) {
        if (!enabled) {
            return false;
        }
        
        TaskProperties task = tasks.get(taskName);
        if (task == null) {
            return true; // 默认启用
        }
        
        return task.isEnabled();
    }

    /**
     * 获取任务 Cron 表达式
     */
    public String getTaskCron(String taskName) {
        TaskProperties task = tasks.get(taskName);
        return task != null ? task.getCron() : null;
    }

    /**
     * 获取任务执行间隔
     */
    public long getTaskRate(String taskName) {
        TaskProperties task = tasks.get(taskName);
        return task != null ? task.getRate() : 0;
    }

    /**
     * 单个任务配置
     */
    public static class TaskProperties {
        
        /**
         * 是否启用此任务
         */
        private boolean enabled = true;

        /**
         * Cron 表达式 (与 rate 二选一)
         */
        private String cron;

        /**
         * 执行间隔 (毫秒)
         */
        private long rate;

        /**
         * 描述
         */
        private String description;

        // Getters and Setters

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getCron() {
            return cron;
        }

        public void setCron(String cron) {
            this.cron = cron;
        }

        public long getRate() {
            return rate;
        }

        public void setRate(long rate) {
            this.rate = rate;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }
    }
}
