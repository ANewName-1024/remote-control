package com.example.user.oidc;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.*;

/**
 * OIDC Token 服务
 * 生成和验证 OIDC 相关 Token
 */
@Service
public class OidcTokenService {

    @Value("${oidc.issuer:http://localhost:8081}")
    private String issuer;

    @Value("${oidc.access-token-expiration:1800000}")
    private Long accessTokenExpiration;

    @Value("${oidc.id-token-expiration:3600000}")
    private Long idTokenExpiration;

    private final KeyPair keyPair;

    public OidcTokenService() throws NoSuchAlgorithmException {
        // 生成 RSA 密钥对用于签名 ID Token
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        this.keyPair = generator.generateKeyPair();
    }

    /**
     * 生成 ID Token (OIDC)
     */
    public String generateIdToken(String subject, String clientId, String nonce, 
                                  Map<String, Object> userInfo) {
        Date now = new Date();
        Date expiryDate = new Date(now.getTime() + idTokenExpiration);

        JwtBuilder builder = Jwts.builder()
                .issuer(issuer)
                .subject(subject)
                .audience().add(clientId).and()
                .issuedAt(now)
                .expiration(expiryDate)
                .id(UUID.randomUUID().toString());

        // 添加标准 OIDC 声明
        builder.claim("auth_time", now.getTime() / 1000);
        
        if (nonce != null) {
            builder.claim("nonce", nonce);
        }

        // 添加用户信息
        if (userInfo != null) {
            for (Map.Entry<String, Object> entry : userInfo.entrySet()) {
                builder.claim(entry.getKey(), entry.getValue());
            }
        }

        // 使用 RSA 私钥签名
        return builder.signWith(keyPair.getPrivate(), Jwts.SIG.RS256).compact();
    }

    /**
     * 生成 Access Token (OAuth 2.0)
     */
    public String generateAccessToken(String subject, String clientId, String scope) {
        Date now = new Date();
        Date expiryDate = new Date(now.getTime() + accessTokenExpiration);

        return Jwts.builder()
                .issuer(issuer)
                .subject(subject)
                .audience().add(clientId).and()
                .issuedAt(now)
                .expiration(expiryDate)
                .claim("scope", scope)
                .claim("token_type", "Bearer")
                .signWith(keyPair.getPrivate(), Jwts.SIG.RS256)
                .compact();
    }

    /**
     * 验证 Access Token
     */
    public boolean validateAccessToken(String token) {
        try {
            parseToken(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 从 Token 获取主题（用户）
     */
    public String getSubjectFromToken(String token) {
        return parseToken(token).getSubject();
    }

    /**
     * 获取用户声明
     */
    public Map<String, Object> getClaims(String token) {
        return parseToken(token);
    }

    /**
     * 获取 OIDC 发现文档
     */
    public Map<String, Object> getDiscoveryDocument() {
        Map<String, Object> doc = new HashMap<>();
        doc.put("issuer", issuer);
        doc.put("authorization_endpoint", issuer + "/oauth/authorize");
        doc.put("token_endpoint", issuer + "/oauth/token");
        doc.put("userinfo_endpoint", issuer + "/oauth/userinfo");
        doc.put("jwks_uri", issuer + "/oauth/jwks");
        doc.put("response_types_supported", Arrays.asList("code", "token", "id_token", "code token", "code id_token", "token id_token", "code token id_token"));
        doc.put("grant_types_supported", Arrays.asList("authorization_code", "client_credentials", "refresh_token", "password"));
        doc.put("subject_types_supported", Arrays.asList("public"));
        doc.put("id_token_signing_alg_values_supported", Arrays.asList("RS256"));
        doc.put("scopes_supported", Arrays.asList("openid", "profile", "email"));
        doc.put("token_endpoint_auth_methods_supported", Arrays.asList("client_secret_basic", "client_secret_post", "none"));
        doc.put("claims_supported", Arrays.asList("sub", "iss", "aud", "exp", "iat", "auth_time", "nonce", "name", "email", "email_verified", "picture"));
        return doc;
    }

    /**
     * 获取 JWKS
     */
    public Map<String, Object> getJwks() {
        Map<String, Object> jwks = new HashMap<>();
        Map<String, Object> key = new HashMap<>();
        
        RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
        key.put("kty", "RSA");
        key.put("use", "sig");
        key.put("alg", "RS256");
        key.put("kid", "default-key");
        key.put("n", Base64.getUrlEncoder().withoutPadding().encodeToString(publicKey.getModulus().toByteArray()));
        key.put("e", Base64.getUrlEncoder().withoutPadding().encodeToString(publicKey.getPublicExponent().toByteArray()));
        
        Map<String, Object> keys = new HashMap<>();
        keys.put("keys", Collections.singletonList(key));
        return keys;
    }

    private Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith((RSAPublicKey) keyPair.getPublic())
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public RSAPublicKey getPublicKey() {
        return (RSAPublicKey) keyPair.getPublic();
    }

    public String getIssuer() {
        return issuer;
    }
}
