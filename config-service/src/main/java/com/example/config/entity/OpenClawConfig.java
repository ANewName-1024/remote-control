package com.example.config.entity;

import jakarta.persistence.*;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * OpenClaw 配置实体
 */
@Data
@Entity
@Table(name = "openclaw_config")
public class OpenClawConfig {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "config_key", nullable = false, unique = true)
    private String configKey;

    @Column(name = "config_value", columnDefinition = "TEXT")
    private String configValue;

    @Column(name = "config_type")
    private String configType;

    @Column(name = "description")
    private String description;

    @Column(name = "is_encrypted")
    private Boolean isEncrypted;

    @Column(name = "created_time")
    private LocalDateTime createdTime;

    @Column(name = "updated_time")
    private LocalDateTime updatedTime;

    @Column(name = "is_deleted")
    private Integer isDeleted;
}
