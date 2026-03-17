package com.example.user.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * OIDC 客户端注册实体
 * 管理 OAuth 2.0 / OIDC 客户端应用
 */
@Entity
@Table(name = "oidc_clients")
public class OidcClient {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "client_id", unique = true, nullable = false)
    private String clientId;

    @Column(name = "client_secret")
    private String clientSecret;

    @Column(name = "client_name")
    private String clientName;

    @Column(name = "client_uri")
    private String clientUri;

    @Column(name = "redirect_uris", columnDefinition = "TEXT")
    private String redirectUris;  // 多个 URI 用逗号分隔

    @Column(name = "grant_types", columnDefinition = "TEXT")
    private String grantTypes;  // authorization_code, client_credentials, refresh_token

    @Column(name = "response_types")
    private String responseTypes;  // code, token, id_token

    @Column(name = "scope")
    private String scope;  // openid, profile, email

    @Column(name = "token_endpoint_auth_method")
    private String tokenEndpointAuthMethod;  // client_secret_basic, client_secret_post, none

    @Column(name = "enabled", nullable = false)
    private Boolean enabled = true;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    // Getters and Setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getClientId() { return clientId; }
    public void setClientId(String clientId) { this.clientId = clientId; }
    public String getClientSecret() { return clientSecret; }
    public void setClientSecret(String clientSecret) { this.clientSecret = clientSecret; }
    public String getClientName() { return clientName; }
    public void setClientName(String clientName) { this.clientName = clientName; }
    public String getClientUri() { return clientUri; }
    public void setClientUri(String clientUri) { this.clientUri = clientUri; }
    public String getRedirectUris() { return redirectUris; }
    public void setRedirectUris(String redirectUris) { this.redirectUris = redirectUris; }
    public String getGrantTypes() { return grantTypes; }
    public void setGrantTypes(String grantTypes) { this.grantTypes = grantTypes; }
    public String getResponseTypes() { return responseTypes; }
    public void setResponseTypes(String responseTypes) { this.responseTypes = responseTypes; }
    public String getScope() { return scope; }
    public void setScope(String scope) { this.scope = scope; }
    public String getTokenEndpointAuthMethod() { return tokenEndpointAuthMethod; }
    public void setTokenEndpointAuthMethod(String tokenEndpointAuthMethod) { this.tokenEndpointAuthMethod = tokenEndpointAuthMethod; }
    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
