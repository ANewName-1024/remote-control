package com.example.config;

import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDateTime;

@Entity
@Table(name = "sys_config")
public class SysConfig {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @NotBlank(message = "配置键不能为空")
    @Column(name = "config_key", unique = true, nullable = false)
    private String configKey;
    
    @NotBlank(message = "配置值不能为空")
    @Column(name = "config_value", columnDefinition = "TEXT")
    private String configValue;
    
    @NotNull(message = "数据类型不能为空")
    @Column(name = "data_type")
    @Enumerated(EnumType.STRING)
    private DataType dataType;
    
    @Column(name = "description")
    private String description;
    
    @Column(name = "is_encrypted")
    private Boolean isEncrypted = false;
    
    @Column(name = "created_by")
    private String createdBy;
    
    @Column(name = "created_time")
    private LocalDateTime createdTime;
    
    @Column(name = "updated_by")
    private String updatedBy;
    
    @Column(name = "updated_time")
    private LocalDateTime updatedTime;
    
    // 0:正常 1:已删除
    @Column(name = "is_deleted")
    private Integer isDeleted = 0;
    
    public enum DataType {
        STRING,     // 字符串
        NUMBER,     // 数字
        BOOLEAN,    // 布尔值
        JSON,       // JSON对象
        LIST,       // 列表
        MAP,        // 键值对
        ENCRYPTED   // 加密文本
    }
    
    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getConfigKey() { return configKey; }
    public void setConfigKey(String configKey) { this.configKey = configKey; }
    public String getConfigValue() { return configValue; }
    public void setConfigValue(String configValue) { this.configValue = configValue; }
    public DataType getDataType() { return dataType; }
    public void setDataType(DataType dataType) { this.dataType = dataType; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public Boolean getIsEncrypted() { return isEncrypted; }
    public void setIsEncrypted(Boolean isEncrypted) { this.isEncrypted = isEncrypted; }
    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String createdBy) { this.createdBy = createdBy; }
    public LocalDateTime getCreatedTime() { return createdTime; }
    public void setCreatedTime(LocalDateTime createdTime) { this.createdTime = createdTime; }
    public String getUpdatedBy() { return updatedBy; }
    public void setUpdatedBy(String updatedBy) { this.updatedBy = updatedBy; }
    public LocalDateTime getUpdatedTime() { return updatedTime; }
    public void setUpdatedTime(LocalDateTime updatedTime) { this.updatedTime = updatedTime; }
    public Integer getIsDeleted() { return isDeleted; }
    public void setIsDeleted(Integer isDeleted) { this.isDeleted = isDeleted; }
}
