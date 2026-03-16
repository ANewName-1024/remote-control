package com.example.config;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "config_history")
public class ConfigHistory {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(name = "config_id")
    private Long configId;
    
    @Column(name = "config_key")
    private String configKey;
    
    @Column(name = "old_value", columnDefinition = "TEXT")
    private String oldValue;
    
    @Column(name = "new_value", columnDefinition = "TEXT")
    private String newValue;
    
    @Column(name = "operation_type")
    @Enumerated(EnumType.STRING)
    private OperationType operationType;
    
    @Column(name = "operator")
    private String operator;
    
    @Column(name = "operation_time")
    private LocalDateTime operationTime;
    
    @Column(name = "remark")
    private String remark;
    
    public enum OperationType {
        CREATE,     // 创建
        UPDATE,     // 更新
        DELETE,     // 删除
        ROLLBACK    // 回滚
    }
    
    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getConfigId() { return configId; }
    public void setConfigId(Long configId) { this.configId = configId; }
    public String getConfigKey() { return configKey; }
    public void setConfigKey(String configKey) { this.configKey = configKey; }
    public String getOldValue() { return oldValue; }
    public void setOldValue(String oldValue) { this.oldValue = oldValue; }
    public String getNewValue() { return newValue; }
    public void setNewValue(String newValue) { this.newValue = newValue; }
    public OperationType getOperationType() { return operationType; }
    public void setOperationType(OperationType operationType) { this.operationType = operationType; }
    public String getOperator() { return operator; }
    public void setOperator(String operator) { this.operator = operator; }
    public LocalDateTime getOperationTime() { return operationTime; }
    public void setOperationTime(LocalDateTime operationTime) { this.operationTime = operationTime; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
}
