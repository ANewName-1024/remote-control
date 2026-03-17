package com.example.user.repository;

import com.example.user.entity.OidcClient;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface OidcClientRepository extends JpaRepository<OidcClient, Long> {
    Optional<OidcClient> findByClientId(String clientId);
    boolean existsByClientId(String clientId);
}
