package com.example.common.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 敏感配置属性
 * 从环境变量或配置中心加载
 */
@Configuration
@ConfigurationProperties(prefix = "secure")
public class SecureProperties {

    /**
     * 加密密钥 (用于配置加密/解密)
     * 通过环境变量 SECURE_MASTER_KEY 注入
     */
    private String masterKey;

    /**
     * 数据库配置
     */
    private Database database = new Database();

    /**
     * JWT 配置
     */
    private Jwt jwt = new Jwt();

    /**
     * Redis 配置
     */
    private Redis redis = new Redis();

    /**
     * OIDC 配置
     */
    private Oidc oidc = new Oidc();

    // Getters and Setters

    public String getMasterKey() {
        return masterKey;
    }

    public void setMasterKey(String masterKey) {
        this.masterKey = masterKey;
    }

    public Database getDatabase() {
        return database;
    }

    public void setDatabase(Database database) {
        this.database = database;
    }

    public Jwt getJwt() {
        return jwt;
    }

    public void setJwt(Jwt jwt) {
        this.jwt = jwt;
    }

    public Redis getRedis() {
        return redis;
    }

    public void setRedis(Redis redis) {
        this.redis = redis;
    }

    public Oidc getOidc() {
        return oidc;
    }

    public void setOidc(Oidc oidc) {
        this.oidc = oidc;
    }

    /**
     * 数据库敏感配置
     */
    public static class Database {
        private String username;
        private String password;
        private String url;

        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }
        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
        public String getUrl() { return url; }
        public void setUrl(String url) { this.url = url; }
    }

    /**
     * JWT 敏感配置
     */
    public static class Jwt {
        private String secret;
        private String publicKey;
        private String privateKey;

        public String getSecret() { return secret; }
        public void setSecret(String secret) { this.secret = secret; }
        public String getPublicKey() { return publicKey; }
        public void setPublicKey(String publicKey) { this.publicKey = publicKey; }
        public String getPrivateKey() { return privateKey; }
        public void setPrivateKey(String privateKey) { this.privateKey = privateKey; }
    }

    /**
     * Redis 敏感配置
     */
    public static class Redis {
        private String password;

        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
    }

    /**
     * OIDC 敏感配置
     */
    public static class Oidc {
        private String clientSecret;
        private String signingKey;

        public String getClientSecret() { return clientSecret; }
        public void setClientSecret(String clientSecret) { this.clientSecret = clientSecret; }
        public String getSigningKey() { return signingKey; }
        public void setSigningKey(String signingKey) { this.signingKey = signingKey; }
    }
}
