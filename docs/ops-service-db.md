# Ops Service 数据表设计

## 概述

ops-service 是运维监控服务，负责告警管理、证书轮换、指标收集等功能。

> 注意：当前版本使用内存存储，如需持久化可扩展为 JPA Entity。

## 数据模型

### 1. Alert - 告警模型

```java
public class Alert {
    private String id;                    // 告警 ID (UUID)
    private AlertType type;              // 告警类型
    private AlertLevel level;            // 告警级别
    private String serviceName;           // 服务名称
    private String message;               // 告警消息
    private Map<String, Object> details;  // 详细信息
    private LocalDateTime timestamp;      // 发生时间
    private boolean acknowledged;         // 是否已确认
}
```

**字段说明**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | String | UUID 唯一标识 |
| type | AlertType | 告警类型 |
| level | AlertLevel | 告警级别 |
| serviceName | String | 相关服务名 |
| message | String | 告警消息 |
| details | Map | 扩展详情 |
| timestamp | LocalDateTime | 发生时间 |
| acknowledged | boolean | 是否已确认 |

---

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

---

### 3. AlertLevel - 告警级别枚举

```java
public enum AlertLevel {
    INFO("信息", 1),
    WARNING("警告", 2),
    CRITICAL("严重", 3);
    
    private final String description;
    private final int priority;
}
```

| 级别 | 描述 | 优先级 |
|------|------|--------|
| INFO | 信息 | 1 |
| WARNING | 警告 | 2 |
| CRITICAL | 严重 | 3 |

---

## 扩展为 JPA Entity (可选)

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
CREATE INDEX idx_alerts_acknowledged ON alerts(acknowledged);
```

---

## 告警处理流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  触发条件   │────>│  生成告警   │────>│  通知渠道   │
│ (Metrics)   │     │  (Alert)    │     │ (Feishu/...)│
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  确认处理   │
                    │ (ACK)       │
                    └─────────────┘
```

---

## 证书管理

### CertificateRotationService

证书轮换服务，负责：
- 定期检查证书有效期
- 自动生成新证书
- 推送新证书到配置中心

**配置参数**：
| 参数 | 说明 | 默认值 |
|------|------|--------|
| cert.check.interval | 证书检查间隔 | 24h |
| cert.expiry.warning.days | 提前告警天数 | 30 |
| cert.rotation.enabled | 是否自动轮换 | false |

---

## 指标收集

### MetricsService

收集的指标类型：
- **JVM 指标**：内存使用、GC、线程数
- **HTTP 指标**：请求延迟、错误率
- **业务指标**：自定义业务指标

**指标存储**：
- 当前版本：内存 + 日志
- 可扩展：InfluxDB / Prometheus
