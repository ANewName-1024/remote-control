package com.example.config;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface ConfigHistoryRepository extends JpaRepository<ConfigHistory, Long> {
    
    List<ConfigHistory> findByConfigIdOrderByOperationTimeDesc(Long configId);
    
    List<ConfigHistory> findByConfigKeyOrderByOperationTimeDesc(String configKey);
}
