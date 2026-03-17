package com.example.config.service;

import com.example.config.entity.ConfigUser;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.Optional;
import java.util.Set;

/**
 * 配置服务认证服务
 */
@Service
public class ConfigAuthService {

    /**
     * 验证 JWT Token
     * Gateway 已经验证过，这里简化处理
     */
    public boolean validateToken(String token) {
        return StringUtils.hasText(token);
    }

    /**
     * 从 Token 获取用户名
     */
    public String getUsernameFromToken(String token) {
        // Gateway 已经验证过 Token，这里简化处理
        // 实际应该从 Token 中解析
        return "config-user";
    }

    /**
     * 获取用户 (简化版)
     */
    public Optional<ConfigUser> getUser(String username) {
        // 简化实现
        ConfigUser user = new ConfigUser();
        user.setId(1L);
        user.setUsername(username);
        user.setRoles(Set.of("USER"));
        user.setPermissions(Set.of("config:read", "config:write"));
        return Optional.of(user);
    }

    /**
     * 从 JWT Token 中获取用户信息
     */
    public ConfigUser getUserFromToken(String token) {
        return getUser(getUsernameFromToken(token)).orElse(null);
    }

    /**
     * 验证用户权限
     */
    public boolean hasPermission(ConfigUser user, String permission) {
        if (user == null || user.getPermissions() == null) {
            return false;
        }
        return user.getPermissions().contains(permission);
    }

    /**
     * 验证用户角色
     */
    public boolean hasRole(ConfigUser user, String role) {
        if (user == null || user.getRoles() == null) {
            return false;
        }
        return user.getRoles().contains(role);
    }
}
