package com.example.config.controller;

import com.example.config.scheduler.SchedulerProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.support.CronExpression;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 定时任务管理控制器
 */
@RestController
@RequestMapping("/scheduler")
public class SchedulerController {

    private static final Logger logger = LoggerFactory.getLogger(SchedulerController.class);

    @Autowired
    private SchedulerProperties schedulerProperties;

    /**
     * 获取定时任务配置
     */
    @GetMapping("/config")
    public Map<String, Object> getSchedulerConfig() {
        Map<String, Object> config = new HashMap<>();
        config.put("enabled", schedulerProperties.isEnabled());
        config.put("tasks", schedulerProperties.getTasks());
        return config;
    }

    /**
     * 更新定时任务全局开关
     */
    @PutMapping("/config/enabled")
    public Map<String, Object> updateEnabled(@RequestParam boolean enabled) {
        schedulerProperties.setEnabled(enabled);
        
        Map<String, Object> result = new HashMap<>();
        result.put("success", true);
        result.put("enabled", enabled);
        result.put("message", enabled ? "定时任务已启用" : "定时任务已禁用");
        
        return result;
    }

    /**
     * 获取所有任务状态
     */
    @GetMapping("/tasks")
    public Map<String, Object> getAllTasks() {
        Map<String, TaskStatus> tasks = new LinkedHashMap<>();
        
        // 内置任务
        tasks.put("config-refresh", new TaskStatus("配置刷新", true, "每5分钟"));
        tasks.put("key-rotation", new TaskStatus("密钥轮换", true, "每天凌晨2点"));
        tasks.put("cleanup", new TaskStatus("数据清理", true, "每天凌晨4点"));
        tasks.put("health-check", new TaskStatus("健康检查", true, "每5分钟"));
        
        // 从配置获取
        schedulerProperties.getTasks().forEach((name, props) -> {
            TaskStatus status = tasks.get(name);
            if (status != null) {
                status.setEnabled(props.isEnabled());
                if (props.getCron() != null) {
                    status.setSchedule(props.getCron());
                } else if (props.getRate() > 0) {
                    status.setSchedule("每" + props.getRate() + "ms");
                }
            }
        });
        
        Map<String, Object> result = new HashMap<>();
        result.put("globalEnabled", schedulerProperties.isEnabled());
        result.put("tasks", tasks);
        
        return result;
    }

    /**
     * 更新单个任务配置
     */
    @PutMapping("/tasks/{taskName}")
    public Map<String, Object> updateTask(
            @PathVariable String taskName,
            @RequestParam(required = false) Boolean enabled,
            @RequestParam(required = false) String cron,
            @RequestParam(required = false) Long rate) {
        
        Map<String, Object> result = new HashMap<>();
        
        // 获取或创建任务配置
        SchedulerProperties.TaskProperties task = schedulerProperties.getTasks().get(taskName);
        if (task == null) {
            task = new SchedulerProperties.TaskProperties();
            schedulerProperties.getTasks().put(taskName, task);
        }
        
        // 更新配置
        if (enabled != null) {
            task.setEnabled(enabled);
        }
        if (cron != null) {
            // 验证 Cron 表达式
            try {
                CronExpression.parse(cron);
                task.setCron(cron);
            } catch (Exception e) {
                result.put("success", false);
                result.put("message", "无效的 Cron 表达式: " + cron);
                return result;
            }
        }
        if (rate != null) {
            task.setRate(rate);
        }
        
        result.put("success", true);
        result.put("message", "任务配置已更新");
        result.put("task", task);
        
        return result;
    }

    /**
     * 手动触发任务执行
     */
    @PostMapping("/tasks/{taskName}/run")
    public Map<String, Object> runTask(@PathVariable String taskName) {
        Map<String, Object> result = new HashMap<>();
        
        if (!schedulerProperties.isTaskEnabled(taskName)) {
            result.put("success", false);
            result.put("message", "任务未启用");
            return result;
        }
        
        logger.info("手动触发定时任务: {}", taskName);
        
        result.put("success", true);
        result.put("message", "任务已触发: " + taskName);
        result.put("triggerTime", LocalDateTime.now());
        
        return result;
    }

    /**
     * 获取任务执行历史 (模拟)
     */
    @GetMapping("/history")
    public Map<String, Object> getHistory(
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String taskName) {
        
        // 模拟历史数据
        List<Map<String, Object>> history = new ArrayList<>();
        
        String[] tasks = {"config-refresh", "key-rotation", "cleanup", "health-check"};
        for (int i = 0; i < Math.min(limit, 20); i++) {
            String task = taskName != null ? taskName : tasks[i % tasks.length];
            
            Map<String, Object> record = new HashMap<>();
            record.put("id", i + 1);
            record.put("taskName", task);
            record.put("startTime", LocalDateTime.now().minusMinutes(i * 10));
            record.put("endTime", LocalDateTime.now().minusMinutes(i * 10).plusSeconds(new Random().nextInt(30)));
            record.put("status", i % 5 == 0 ? "FAILED" : "SUCCESS");
            record.put("duration", new Random().nextInt(5000));
            
            history.add(record);
        }
        
        Map<String, Object> result = new HashMap<>();
        result.put("total", history.size());
        result.put("history", history);
        
        return result;
    }

    /**
     * 获取调度器状态
     */
    @GetMapping("/status")
    public Map<String, Object> getStatus() {
        Map<String, Object> status = new HashMap<>();
        status.put("enabled", schedulerProperties.isEnabled());
        status.put("taskCount", schedulerProperties.getTasks().size());
        status.put("timestamp", LocalDateTime.now());
        
        return status;
    }

    /**
     * 任务状态内部类
     */
    private static class TaskStatus {
        private String name;
        private boolean enabled;
        private String schedule;
        private String description;

        public TaskStatus(String name, boolean enabled, String schedule) {
            this.name = name;
            this.enabled = enabled;
            this.schedule = schedule;
        }

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) { this.enabled = enabled; }
        public String getSchedule() { return schedule; }
        public void setSchedule(String schedule) { this.schedule = schedule; }
        public String getDescription() { return description; }
        public void setDescription(String description) { this.description = description; }
    }
}
