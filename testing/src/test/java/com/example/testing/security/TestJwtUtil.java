package com.example.testing.security;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * 测试用 JWT 工具类
 */
public class TestJwtUtil {

    private static final String SECRET = "testSecretKeyForJWTTokenGenerationMustBeLongEnough12345";
    private static final SecretKey KEY = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));

    /**
     * 生成测试用 JWT Token
     */
    public static String generateToken(String username, Long userId, Collection<String> roles) {
        Map<String, Object> claims = new HashMap<>();
        claims.put("userId", userId);
        claims.put("roles", roles);

        return Jwts.builder()
                .setClaims(claims)
                .setSubject(username)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + 3600000)) // 1 hour
                .signWith(KEY, SignatureAlgorithm.HS256)
                .compact();
    }

    /**
     * 生成带权限的 JWT Token
     */
    public static String generateToken(String username, Long userId, 
            Collection<String> roles, Collection<String> permissions) {
        Map<String, Object> claims = new HashMap<>();
        claims.put("userId", userId);
        claims.put("roles", roles);
        claims.put("permissions", permissions);

        return Jwts.builder()
                .setClaims(claims)
                .setSubject(username)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() + 3600000))
                .signWith(KEY, SignatureAlgorithm.HS256)
                .compact();
    }

    /**
     * 生成过期的 Token
     */
    public static String generateExpiredToken(String username) {
        return Jwts.builder()
                .setSubject(username)
                .setIssuedAt(new Date())
                .setExpiration(new Date(System.currentTimeMillis() - 3600000)) // Expired
                .signWith(KEY, SignatureAlgorithm.HS256)
                .compact();
    }

    /**
     * 生成管理员 Token
     */
    public static String generateAdminToken() {
        return generateToken("admin", 1L, List.of("ADMIN"), List.of("*:*:*"));
    }

    /**
     * 生成普通用户 Token
     */
    public static String generateUserToken() {
        return generateToken("testuser", 2L, List.of("USER"), List.of("user:read"));
    }

    /**
     * 生成 Authorization Header
     */
    public static String authHeader(String token) {
        return "Bearer " + token;
    }

    /**
     * 生成管理员 Authorization Header
     */
    public static String adminAuthHeader() {
        return authHeader(generateAdminToken());
    }

    /**
     * 生成用户 Authorization Header
     */
    public static String userAuthHeader() {
        return authHeader(generateUserToken());
    }
}
