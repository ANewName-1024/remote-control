package com.example.config.repository;

import com.example.config.entity.OpenClawConfig;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface OpenClawConfigRepository extends JpaRepository<OpenClawConfig, Long> {

    Optional<OpenClawConfig> findByConfigKey(String configKey);
}
