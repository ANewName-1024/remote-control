package com.example.user.repository;

import com.example.user.entity.OidcAuthorizationCode;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface OidcAuthorizationCodeRepository extends JpaRepository<OidcAuthorizationCode, Long> {
    Optional<OidcAuthorizationCode> findByCode(String code);
    
    @Modifying
    @Query("DELETE FROM OidcAuthorizationCode a WHERE a.expiresAt < CURRENT_TIMESTAMP OR a.used = true")
    void deleteExpiredOrUsed();
}
