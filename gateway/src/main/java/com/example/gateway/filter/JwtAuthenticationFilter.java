package com.example.gateway.filter;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

/**
 * JWT 认证全局过滤器
 */
@Component
public class JwtAuthenticationFilter implements GlobalFilter, Ordered {

    @Value("${jwt.secret:}")
    private String jwtSecret;

    @Value("${jwt.exclude-paths:}")
    private String excludePaths;

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();
        String path = request.getURI().getPath();

        // 检查是否跳过认证
        if (shouldSkipAuthentication(path)) {
            return chain.filter(exchange);
        }

        // 获取 Token
        String token = getTokenFromRequest(request);

        if (token == null) {
            return unauthorized(exchange.getResponse(), "未提供认证令牌");
        }

        // 验证 Token
        try {
            if (validateToken(token)) {
                // 将用户信息添加到请求头传递给下游服务
                Claims claims = getClaims(token);
                ServerHttpRequest modifiedRequest = request.mutate()
                        .header("X-User-Id", String.valueOf(claims.get("userId")))
                        .header("X-User-Name", claims.getSubject())
                        .build();
                
                return chain.filter(exchange.mutate().request(modifiedRequest).build());
            } else {
                return unauthorized(exchange.getResponse(), "令牌无效或已过期");
            }
        } catch (Exception e) {
            return unauthorized(exchange.getResponse(), "令牌验证失败: " + e.getMessage());
        }
    }

    /**
     * 检查是否跳过认证
     */
    private boolean shouldSkipAuthentication(String path) {
        if (!StringUtils.hasText(excludePaths)) {
            return false;
        }

        List<String> paths = Arrays.asList(excludePaths.split(","));
        for (String pattern : paths) {
            if (path.matches(pattern.trim().replace("**", ".*"))) {
                return true;
            }
        }
        return false;
    }

    /**
     * 从请求中获取 Token
     */
    private String getTokenFromRequest(ServerHttpRequest request) {
        String bearerToken = request.getHeaders().getFirst("Authorization");
        if (StringUtils.hasText(bearerToken) && bearerToken.startsWith("Bearer ")) {
            return bearerToken.substring(7);
        }
        return null;
    }

    /**
     * 验证 Token
     */
    private boolean validateToken(String token) {
        try {
            if (!StringUtils.hasText(jwtSecret)) {
                // 如果未配置密钥，跳过验证（仅用于测试）
                return true;
            }
            getClaims(token);
            return true;
        } catch (JwtException e) {
            return false;
        }
    }

    /**
     * 解析 Token 获取 Claims
     */
    private Claims getClaims(String token) {
        SecretKey key = Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
        return io.jsonwebtoken.Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    /**
     * 返回未授权响应
     */
    private Mono<Void> unauthorized(ServerHttpResponse response, String message) {
        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().add("Content-Type", "application/json");
        String body = "{\"error\":\"" + message + "\"}";
        return response.writeWith(Mono.just(response.bufferFactory().wrap(body.getBytes(StandardCharsets.UTF_8))));
    }

    @Override
    public int getOrder() {
        // 在其他过滤器之前执行
        return -100;
    }
}
