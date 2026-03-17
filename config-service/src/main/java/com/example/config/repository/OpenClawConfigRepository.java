package com.example.config.repository;

import com.example.config.entity.OpenClawConfig;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface OpenClawConfigRepository extends JpaRepository<OpenClawConfig, Long> {

    Optional<OpenClawConfig> findByConfigKey(String configKey);

    List<OpenClawConfig> findByConfigType(OpenClawConfig.ConfigType configType);

    List<OpenClawConfig> findByIsEncryptedTrue();

    @Query("SELECT c FROM OpenClawConfig c WHERE c.isDeleted = 0")
    List<OpenClawConfig> findAllActive();

    boolean existsByConfigKey(String configKey);

    void deleteByConfigKey(String configKey);
}
