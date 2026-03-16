package com.example.config;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface SysConfigRepository extends JpaRepository<SysConfig, Long> {
    
    Optional<SysConfig> findByConfigKeyAndIsDeleted(String configKey, Integer isDeleted);
    
    List<SysConfig> findByIsDeleted(Integer isDeleted);
    
    boolean existsByConfigKeyAndIsDeleted(String configKey, Integer isDeleted);
}
