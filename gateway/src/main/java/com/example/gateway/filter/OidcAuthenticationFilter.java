package com.example.gateway.filter;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * OIDC JWT 认证过滤器
 * 支持验证 OIDC 颁发的 Token
 */
@Component
public class OidcAuthenticationFilter implements GlobalFilter, Ordered {

    @Value("${oidc.jwks-uri:http://localhost:8081/oauth/jwks}")
    private String jwksUri;

    @Value("${oidc.issuer:http://localhost:8081}")
    private String issuer;

    @Value("${jwt.exclude-paths:}")
    private String excludePaths;

    private final WebClient webClient;
    private final Map<String, RSAPublicKey> keyCache = new ConcurrentHashMap<>();

    public OidcAuthenticationFilter() {
        this.webClient = WebClient.builder().build();
    }

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
            Claims claims = validateToken(token);
            if (claims != null) {
                // 将用户信息添加到请求头
                ServerHttpRequest modifiedRequest = request.mutate()
                        .header("X-User-Id", String.valueOf(claims.get("userId")))
                        .header("X-User-Name", claims.getSubject())
                        .header("X-Token-Claims", Base64.getUrlEncoder().encodeToString(
                                claims.toString().getBytes(StandardCharsets.UTF_8)))
                        .build();
                
                return chain.filter(exchange.mutate().request(modifiedRequest).build());
            } else {
                return unauthorized(exchange.getResponse(), "令牌无效");
            }
        } catch (Exception e) {
            return unauthorized(exchange.getResponse(), "令牌验证失败: " + e.getMessage());
        }
    }

    /**
     * 验证 Token
     */
    private Claims validateToken(String token) {
        try {
            // 解析 Token 获取 kid
            String[] parts = token.split("\\.");
            if (parts.length != 3) {
                return null;
            }

            // 解析 Header
            String headerJson = new String(Base64.getUrlDecoder().decode(parts[0]));
            Map<String, Object> header = parseJson(headerJson);
            String kid = (String) header.get("kid");

            // 获取公钥
            RSAPublicKey publicKey = getPublicKey(kid);
            if (publicKey == null) {
                // 如果没有 kid，尝试获取第一个公钥
                publicKey = getPublicKey(null);
            }

            if (publicKey == null) {
                throw new RuntimeException("无法获取公钥");
            }

            // 验证 Token
            return io.jsonwebtoken.Jwts.parser()
                    .verifyWith(publicKey)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();

        } catch (JwtException e) {
            return null;
        }
    }

    /**
     * 获取公钥
     */
    private RSAPublicKey getPublicKey(String kid) {
        // 先从缓存获取
        if (kid != null && keyCache.containsKey(kid)) {
            return keyCache.get(kid);
        }
        if (kid == null && !keyCache.isEmpty()) {
            return keyCache.values().iterator().next();
        }

        try {
            // 从 JWKS URI 获取
            String jwksJson = webClient.get()
                    .uri(jwksUri)
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            if (jwksJson != null) {
                Map<String, Object> jwks = parseJson(jwksJson);
                List<Map<String, Object>> keys = (List<Map<String, Object>>) jwks.get("keys");

                if (keys != null) {
                    for (Map<String, Object> key : keys) {
                        String keyId = (String) key.get("kid");
                        RSAPublicKey publicKey = parsePublicKey(key);
                        if (publicKey != null) {
                            keyCache.put(keyId, publicKey);
                        }
                    }
                }
            }

            return kid != null ? keyCache.get(kid) : keyCache.values().iterator().next();

        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 解析公钥
     */
    private RSAPublicKey parsePublicKey(Map<String, Object> key) {
        try {
            String kty = (String) key.get("kty");
            if (!"RSA".equals(kty)) {
                return null;
            }

            String n = (String) key.get("n");
            String e = (String) key.get("e");

            byte[] nBytes = Base64.getUrlDecoder().decode(n);
            byte[] eBytes = Base64.getUrlDecoder().decode(e);

            java.math.BigInteger modulus = new java.math.BigInteger(1, nBytes);
            java.math.BigInteger exponent = new java.math.BigInteger(1, eBytes);

            java.security.spec.RSAPublicKeySpec spec = 
                    new java.security.spec.RSAPublicKeySpec(modulus, exponent);
            java.security.KeyFactory factory = java.security.KeyFactory.getInstance("RSA");
            return (RSAPublicKey) factory.generatePublic(spec);

        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 解析 JSON
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> parseJson(String json) {
        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
        try {
            return mapper.readValue(json, Map.class);
        } catch (Exception e) {
            return Map.of();
        }
    }

    /**
     * 检查是否跳过认证
     */
    private boolean shouldSkipAuthentication(String path) {
        if (!StringUtils.hasText(excludePaths)) {
            return false;
        }

        for (String pattern : excludePaths.split(",")) {
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
        return -100;
    }
}
