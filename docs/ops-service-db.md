# Ops Service 数据表设计

## 概述

ops-service 是运维监控服务，负责告警管理、证书轮换、指标收集等功能。

## 数据模型

### 1. Alert - 告警模型

```java
public class Alert {
    private String id;
    private AlertType type;
    private AlertLevel level;
    private String serviceName;
    private String message;
    private Map<String, Object> details;
    private LocalDateTime timestamp;
    private boolean acknowledged;
}
```

### 2. AlertType - 告警类型枚举

```java
public enum AlertType {
    ERROR_RATE,        // 错误率告警
    RESPONSE_TIME,    // 响应时间告警
    SERVICE_DOWN,     // 服务宕机
    MEMORY_USAGE,     // 内存使用率
    CPU_USAGE,        // CPU 使用率
    THREAD_POOL,      // 线程池告警
    DATABASE_POOL     // 数据库连接池告警
}
```

### 3. AlertLevel - 告警级别枚举

```java
public enum AlertLevel {
    INFO("信息", 1),
    WARNING("警告", 2),
    CRITICAL("严重", 3);
}
```

## 可选持久化表

如需持久化到数据库，可创建以下表：

```sql
CREATE TABLE alerts (
    id VARCHAR(36) PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    level VARCHAR(20) NOT NULL,
    service_name VARCHAR(100),
    message TEXT NOT NULL,
    details JSONB,
    timestamp TIMESTAMP NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alerts_type ON alerts(type);
CREATE INDEX idx_alerts_level ON alerts(level);
CREATE INDEX idx_alerts_service ON alerts(service_name);
CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);
```

## 技术栈

- Spring Boot: 3.5.0
- Spring Cloud: 2025.0.0
- Nacos: 可选集成
- Spring Cloud Sleuth: 分布式追踪

## 功能特性

- 告警管理
- 证书轮换
- 指标收集
- 分布式追踪 (Sleuth)
- Nacos 可选集成
