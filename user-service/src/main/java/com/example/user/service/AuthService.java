package com.example.user.service;

import com.example.user.dto.LoginRequest;
import com.example.user.dto.LoginResponse;
import com.example.user.dto.RegisterRequest;
import com.example.user.entity.Permission;
import com.example.user.entity.RefreshToken;
import com.example.user.entity.Role;
import com.example.user.entity.User;
import com.example.user.repository.PermissionRepository;
import com.example.user.repository.RefreshTokenRepository;
import com.example.user.repository.RoleRepository;
import com.example.user.repository.UserRepository;
import com.example.user.security.JwtUtil;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.regex.Pattern;

/**
 * 认证服务
 */
@Service
public class AuthService {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private RoleRepository roleRepository;

    @Autowired
    private PermissionRepository permissionRepository;

    @Autowired
    private RefreshTokenRepository refreshTokenRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtUtil jwtUtil;

    @Value("${jwt.expiration:1800000}")
    private Long accessTokenExpiration;

    @Value("${jwt.refresh-expiration:604800000}")
    private Long refreshTokenExpiration;

    @Value("${auth.register.invite-code-required:false}")
    private boolean inviteCodeRequired;

    @Value("${auth.register.invite-codes:}")
    private String inviteCodes;

    // 弱密码字典
    private static final Set<String> WEAK_PASSWORDS = new HashSet<>(Arrays.asList(
            // 常见弱密码
            "123456", "password", "12345678", "qwerty", "123456789",
            "12345", "1234", "111111", "1234567", "dragon",
            "123123", "baseball", "abc123", "football", "monkey",
            "letmein", "shadow", "master", "666666", "qwertyuiop",
            "123321", "mustang", "1234567890", "michael", "654321",
            "superman", "1qaz2wsx", "7777777", "121212", "000000",
            "qazwsx", "123qwe", "killer", "trustno1", "jordan",
            "jennifer", "zxcvbnm", "asdfgh", "hunter", "buster",
            "soccer", "harley", "batman", "andrew", "tigger",
            "sunshine", "iloveyou", "2000", "charlie", "robert",
            "thomas", "hockey", "ranger", "daniel", "starwars",
            "klaster", "112233", "george", "computer", "michael",
            "john", "essex", "michelle", "ginger", "maggie",
            "159753", "aaaaaa", "christin", "Kimberly",
            "schumacher", "taylor", "matrix",
            // 常见模式
            "password1", "password123", "admin123", "welcome123",
            "changeme", "default", "root", "toor", "passw0rd",
            "p@ssword", "p@ssw0rd", "passw0rd!",
            "Admin@123", "Admin123", "admin@123", "Root@123", "Test@123",
            // 键盘模式
            "1q2w3e4r", "1qaz2wsx", "qweasdzxc", "asdfghjkl",
            "zxcvbnm", "1qaz@WSX", "qwe@123", "asd@123",
            // 纯数字变体
            "000000", "111111", "222222", "333333", "444444",
            "555555", "666666", "777777", "888888", "999999",
            "0123456789", "9876543210",
            // 公司常见
            "company123", "password1!", "P@ssword1!", "Welcome1!",
            // 季节日期
            "Summer2024", "Spring2024", "Winter2024", "Autumn2024",
            "2024Pass", "2024Password", "Pass2024"
    ));

    // 密码强度正则：至少8位，包含数字和字母
    private static final Pattern PASSWORD_PATTERN = 
            Pattern.compile("^(?=.*[A-Za-z])(?=.*\\d)[A-Za-z\\d@$!%*#?&]{8,}$");

    /**
     * 用户注册
     */
    @Transactional
    public User register(RegisterRequest request) {
        if (request.getUsername() == null || request.getUsername().trim().isEmpty()) {
            throw new RuntimeException("用户名不能为空");
        }
        if (request.getPassword() == null || request.getPassword().trim().isEmpty()) {
            throw new RuntimeException("密码不能为空");
        }

        if (userRepository.existsByUsername(request.getUsername())) {
            throw new RuntimeException("用户名已存在");
        }

        if (inviteCodeRequired) {
            String inviteCode = request.getInviteCode();
            if (inviteCode == null || !isValidInviteCode(inviteCode)) {
                throw new RuntimeException("邀请码无效");
            }
        }

        // 验证密码强度
        validatePasswordStrength(request.getPassword());

        if (!isValidUsername(request.getUsername())) {
            throw new RuntimeException("用户名格式不正确，只允许字母、数字、下划线");
        }

        User user = new User(
            request.getUsername(),
            request.getEmail(),
            passwordEncoder.encode(request.getPassword())
        );

        Role userRole = roleRepository.findByName("USER")
                .orElseGet(() -> {
                    Role newRole = new Role("USER", "普通用户");
                    Set<Permission> perms = new HashSet<>();
                    perms.add(permissionRepository.findByName("user:read")
                            .orElseGet(() -> permissionRepository.save(new Permission("user:read", "读取用户"))));
                    newRole.setPermissions(perms);
                    return roleRepository.save(newRole);
                });

        user.getRoles().add(userRole);
        return userRepository.save(user);
    }

    private boolean isValidInviteCode(String code) {
        if (inviteCodes == null || inviteCodes.isEmpty()) return false;
        for (String c : inviteCodes.split(",")) {
            if (c.trim().equals(code)) return true;
        }
        return false;
    }

    /**
     * 验证密码强度
     */
    private void validatePasswordStrength(String password) {
        if (password == null || password.length() < 8) {
            throw new RuntimeException("密码长度至少8位");
        }

        // 检查是否包含数字
        if (!password.matches(".*\\d.*")) {
            throw new RuntimeException("密码必须包含数字");
        }

        // 检查是否包含字母
        if (!password.matches(".*[a-zA-Z].*")) {
            throw new RuntimeException("密码必须包含字母");
        }

        // 检查弱密码
        String lowerPassword = password.toLowerCase();
        if (WEAK_PASSWORDS.contains(lowerPassword)) {
            throw new RuntimeException("密码太简单，请使用更复杂的密码");
        }

        // 检查键盘连续字符
        if (hasSequentialChars(password)) {
            throw new RuntimeException("密码不能包含连续字符");
        }

        // 检查重复字符
        if (hasRepeatedChars(password)) {
            throw new RuntimeException("密码不能包含过多重复字符");
        }
    }

    /**
     * 检查键盘连续字符
     */
    private boolean hasSequentialChars(String password) {
        String lower = password.toLowerCase();
        String[] sequences = {
                "1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm",
                "abcdefghijklmnopqrstuvwxyz", "0123456789",
                "qazwsxedc", "plmoknijb", "ujmki"
        };

        for (String seq : sequences) {
            for (int i = 0; i < seq.length() - 2; i++) {
                String sub = seq.substring(i, i + 3);
                if (lower.contains(sub)) {
                    return true;
                }
            }
        }
        return false;
    }

    /**
     * 检查重复字符
     */
    private boolean hasRepeatedChars(String password) {
        for (int i = 0; i < password.length() - 2; i++) {
            if (password.charAt(i) == password.charAt(i + 1) &&
                    password.charAt(i) == password.charAt(i + 2)) {
                return true;
            }
        }
        return false;
    }

    private boolean isValidUsername(String username) {
        return Pattern.matches("^[a-zA-Z0-9_]{3,20}$", username);
    }

    /**
     * 用户登录
     */
    public LoginResponse login(LoginRequest request) {
        User user = userRepository.findByUsername(request.getUsername())
                .orElseThrow(() -> new RuntimeException("用户名或密码错误"));

        if (!passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new RuntimeException("用户名或密码错误");
        }

        if (!user.getEnabled()) {
            throw new RuntimeException("账号已被禁用");
        }

        Set<String> roles = new HashSet<>();
        for (Role role : user.getRoles()) {
            roles.add(role.getName());
        }
        String accessToken = jwtUtil.generateToken(
            user.getUsername(),
            user.getId(),
            roles,
            user.getPermissions()
        );

        String refreshTokenValue = UUID.randomUUID().toString().replace("-", "");
        RefreshToken refreshToken = new RefreshToken(refreshTokenValue, user, 
            LocalDateTime.now().plusNanos(refreshTokenExpiration * 1_000_000));
        refreshTokenRepository.save(refreshToken);

        return new LoginResponse(
            accessToken,
            refreshTokenValue,
            user.getUsername(),
            user.getEmail(),
            user.getId(),
            accessTokenExpiration / 1000,
            refreshTokenExpiration / 1000
        );
    }

    /**
     * 使用 Refresh Token 刷新 Access Token
     */
    public LoginResponse refreshToken(String refreshTokenValue) {
        RefreshToken refreshToken = refreshTokenRepository.findByToken(refreshTokenValue)
                .orElseThrow(() -> new RuntimeException("Refresh Token 无效"));

        if (!refreshToken.isValid()) {
            throw new RuntimeException("Refresh Token 已过期或已撤销");
        }

        User user = refreshToken.getUser();
        if (!user.getEnabled()) {
            throw new RuntimeException("账号已被禁用");
        }

        refreshToken.setRevoked(true);
        refreshTokenRepository.save(refreshToken);

        Set<String> roles = new HashSet<>();
        for (Role role : user.getRoles()) {
            roles.add(role.getName());
        }
        String accessToken = jwtUtil.generateToken(
            user.getUsername(),
            user.getId(),
            roles,
            user.getPermissions()
        );

        String newRefreshTokenValue = UUID.randomUUID().toString().replace("-", "");
        RefreshToken newRefreshToken = new RefreshToken(newRefreshTokenValue, user,
            LocalDateTime.now().plusNanos(refreshTokenExpiration * 1_000_000));
        refreshTokenRepository.save(newRefreshToken);

        return new LoginResponse(
            accessToken,
            newRefreshTokenValue,
            user.getUsername(),
            user.getEmail(),
            user.getId(),
            accessTokenExpiration / 1000,
            refreshTokenExpiration / 1000
        );
    }

    @Transactional
    public void revokeToken(String refreshTokenValue) {
        refreshTokenRepository.findByToken(refreshTokenValue).ifPresent(token -> {
            token.setRevoked(true);
            refreshTokenRepository.save(token);
        });
    }

    @Transactional
    public void revokeAllUserTokens(Long userId) {
        refreshTokenRepository.revokeAllByUserId(userId);
    }

    @Transactional
    public void cleanupExpiredTokens() {
        refreshTokenRepository.deleteExpiredOrRevoked(LocalDateTime.now());
    }

    public User getCurrentUser(String username) {
        return userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("用户不存在"));
    }

    public boolean hasPermission(String username, String permission) {
        User user = userRepository.findByUsername(username).orElse(null);
        if (user == null) return false;
        return user.getPermissions().contains(permission);
    }

    public boolean hasRole(String username, String roleName) {
        User user = userRepository.findByUsername(username).orElse(null);
        if (user == null) return false;
        return user.getRoles().stream()
                .anyMatch(r -> r.getName().equalsIgnoreCase(roleName));
    }
}
