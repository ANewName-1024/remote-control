package com.example.ops.controller;

import com.example.ops.security.JwtUtil;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import java.util.regex.Pattern;

/**
 * 认证控制器
 */
@RestController
@RequestMapping("/ops/auth")
public class AuthController {

    @Autowired
    private JwtUtil jwtUtil;

    private static final org.springframework.security.crypto.password.PasswordEncoder passwordEncoder = 
            new org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder();
    
    // 密码强度正则：至少8位，包含数字和字母
    private static final Pattern PASSWORD_PATTERN = Pattern.compile("^(?=.*[A-Za-z])(?=.*\\d)[A-Za-z\\d@$!%*#?&]{8,}$");
    
    /**
     * 验证密码强度
     */
    private boolean isPasswordStrong(String password) {
        return password != null && PASSWORD_PATTERN.matcher(password).matches();
    }
    
    /**
     * 默认用户 (生产环境应从数据库读取)
     * 密码要求：至少8位，包含数字和字母
     */
    private static final Map<String, UserCredential> USERS = new HashMap<>();
    
    static {
        // 默认用户: admin (密码: Admin@123456)
        USERS.put("admin", new UserCredential(1L, "admin", passwordEncoder.encode("Admin@123456"), 
                List.of("ADMIN"), List.of("ops:view", "ops:manage", "admin:manage")));
        // 运维人员: ops (密码: Ops@123456)
        USERS.put("ops", new UserCredential(2L, "ops", passwordEncoder.encode("Ops@123456"), 
                List.of("OPS"), List.of("ops:view", "ops:manage")));
        // 监控人员: monitor (密码: Monitor@123456)
        USERS.put("monitor", new UserCredential(3L, "monitor", passwordEncoder.encode("Monitor@123456"), 
                List.of("MONITOR"), List.of("ops:view")));
    }

    /**
     * 登录
     */
    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody LoginRequest request) {
        // 验证密码强度
        if (!isPasswordStrong(request.getPassword())) {
            throw new RuntimeException("密码强度不足，需至少8位，包含数字和字母");
        }
        
        UserCredential user = USERS.get(request.getUsername());
        
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new RuntimeException("用户名或密码错误");
        }

        String token = jwtUtil.generateToken(user.getUsername(), user.getUserId(), user.getRoles(), user.getPermissions());
        
        Map<String, Object> result = new HashMap<>();
        result.put("token", token);
        result.put("username", user.getUsername());
        result.put("roles", user.getRoles());
        result.put("permissions", user.getPermissions());
        result.put("expiresIn", 86400); // 24小时
        
        return result;
    }

    /**
     * 获取当前用户信息
     */
    @GetMapping("/me")
    public Map<String, Object> getCurrentUser(@RequestHeader("Authorization") String authHeader) {
        String token = authHeader.substring(7);
        
        if (!jwtUtil.validateToken(token)) {
            throw new RuntimeException("无效的 token");
        }

        String username = jwtUtil.getUsernameFromToken(token);
        Long userId = jwtUtil.getUserIdFromToken(token);
        List<String> roles = jwtUtil.getRolesFromToken(token);
        List<String> permissions = jwtUtil.getPermissionsFromToken(token);

        Map<String, Object> result = new HashMap<>();
        result.put("userId", userId);
        result.put("username", username);
        result.put("roles", roles);
        result.put("permissions", permissions);
        
        return result;
    }

    /**
     * 验证 Token
     */
    @GetMapping("/validate")
    public Map<String, Object> validate(@RequestHeader("Authorization") String authHeader) {
        String token = authHeader.substring(7);
        boolean valid = jwtUtil.validateToken(token);
        
        Map<String, Object> result = new HashMap<>();
        result.put("valid", valid);
        
        if (valid) {
            result.put("username", jwtUtil.getUsernameFromToken(token));
        }
        
        return result;
    }

    /**
     * 登录请求
     */
    public static class LoginRequest {
        private String username;
        private String password;

        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
    }

    /**
     * 用户凭证
     */
    private static class UserCredential {
        private Long userId;
        private String username;
        private String password;
        private List<String> roles;
        private List<String> permissions;

        public UserCredential(Long userId, String username, String password, List<String> roles, List<String> permissions) {
            this.userId = userId;
            this.username = username;
            this.password = password;
            this.roles = roles;
            this.permissions = permissions;
        }

        public Long getUserId() { return userId; }
        public String getUsername() { return username; }
        public String getPassword() { return password; }
        public List<String> getRoles() { return roles; }
        public List<String> getPermissions() { return permissions; }
    }
}
