package com.example.config.entity;

import java.util.Set;

/**
 * 配置服务用户实体
 * 用于从 JWT 中解析用户信息
 */
public class ConfigUser {

    private Long id;
    private String username;
    private Set<String> roles;
    private Set<String> permissions;
    private Boolean enabled = true;

    public ConfigUser() {}

    public ConfigUser(Long id, String username, Set<String> roles, Set<String> permissions) {
        this.id = id;
        this.username = username;
        this.roles = roles;
        this.permissions = permissions;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public Set<String> getRoles() { return roles; }
    public void setRoles(Set<String> roles) { this.roles = roles; }

    public Set<String> getPermissions() { return permissions; }
    public void setPermissions(Set<String> permissions) { this.permissions = permissions; }

    public Boolean getEnabled() { return enabled; }
    public void setEnabled(Boolean enabled) { this.enabled = enabled; }
}
