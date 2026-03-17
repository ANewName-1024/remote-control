package com.example.config;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

@Repository
public interface ConfigHistoryRepository extends JpaRepository<ConfigHistory, Long> {
    
    List<ConfigHistory> findByConfigIdOrderByOperationTimeDesc(Long configId);
    
    List<ConfigHistory> findByConfigKeyOrderByOperationTimeDesc(String configKey);
    
    // ========== 定时任务需要的方法 ==========
    
    int deleteByOperationTimeBefore(LocalDateTime dateTime);
    
    @Query("SELECT COUNT(h) FROM ConfigHistory h WHERE h.operationTime < :dateTime")
    int countByOperationTimeBefore(LocalDateTime dateTime);
    
    List<ConfigHistory> findByOperationTimeBefore(LocalDateTime dateTime);
    
    @Modifying
    @Query("DELETE FROM ConfigHistory h WHERE h.id IN (SELECT ch.id FROM ConfigHistory ch WHERE ch.operationTime < :dateTime)")
    int deleteOldRecords(LocalDateTime dateTime);
}
