package com.example.user.oidc;

import com.example.user.entity.*;
import com.example.user.repository.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.*;

/**
 * OIDC 授权服务
 * 实现 OAuth 2.0 / OIDC 授权流程
 */
@Service
public class OidcAuthorizationService {

    @Autowired
    private OidcClientRepository clientRepository;

    @Autowired
    private OidcAuthorizationCodeRepository authorizationCodeRepository;

    @Autowired
    private RefreshTokenRepository refreshTokenRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OidcTokenService tokenService;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Value("${oidc.authorization-code-expiration:600000}")
    private Long authorizationCodeExpiration;

    /**
     * 验证客户端
     */
    public OidcClient validateClient(String clientId, String redirectUri) {
        OidcClient client = clientRepository.findByClientId(clientId)
                .orElseThrow(() -> new RuntimeException("客户端不存在"));

        if (!client.getEnabled()) {
            throw new RuntimeException("客户端已禁用");
        }

        // 验证 redirect_uri
        String[] uris = client.getRedirectUris().split(",");
        boolean validUri = false;
        for (String uri : uris) {
            if (uri.trim().equals(redirectUri)) {
                validUri = true;
                break;
            }
        }

        if (!validUri) {
            throw new RuntimeException("redirect_uri 无效");
        }

        return client;
    }

    /**
     * 生成授权码
     */
    @Transactional
    public String generateAuthorizationCode(String clientId, String redirectUri, 
                                           String username, String scope,
                                           String nonce, String state,
                                           String codeChallenge, String codeChallengeMethod) {
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("用户不存在"));

        // 生成授权码
        String code = UUID.randomUUID().toString().replace("-", "");

        OidcAuthorizationCode authCode = new OidcAuthorizationCode();
        authCode.setCode(code);
        authCode.setUser(user);
        authCode.setClientId(clientId);
        authCode.setRedirectUri(redirectUri);
        authCode.setScope(scope);
        authCode.setNonce(nonce);
        authCode.setState(state);
        authCode.setCodeChallenge(codeChallenge);
        authCode.setCodeChallengeMethod(codeChallengeMethod);
        authCode.setExpiresAt(LocalDateTime.now().plusNanos(authorizationCodeExpiration * 1_000_000));
        
        authorizationCodeRepository.save(authCode);

        return code;
    }

    /**
     * 使用授权码兑换 Token
     */
    @Transactional
    public Map<String, Object> exchangeCodeForTokens(String code, String clientId, 
                                                     String clientSecret, String redirectUri,
                                                     String codeVerifier) {
        // 验证客户端
        OidcClient client = clientRepository.findByClientId(clientId)
                .orElseThrow(() -> new RuntimeException("客户端不存在"));
        
        if (!client.getEnabled()) {
            throw new RuntimeException("客户端已禁用");
        }

        // 验证客户端密钥
        if (!passwordEncoder.matches(clientSecret, client.getClientSecret())) {
            throw new RuntimeException("客户端密钥错误");
        }

        // 验证授权码
        OidcAuthorizationCode authCode = authorizationCodeRepository.findByCode(code)
                .orElseThrow(() -> new RuntimeException("授权码无效"));

        if (authCode.getUsed()) {
            throw new RuntimeException("授权码已被使用");
        }

        if (authCode.isExpired()) {
            throw new RuntimeException("授权码已过期");
        }

        if (!authCode.getClientId().equals(clientId)) {
            throw new RuntimeException("客户端不匹配");
        }

        if (!authCode.getRedirectUri().equals(redirectUri)) {
            throw new RuntimeException("redirect_uri 不匹配");
        }

        // 验证 PKCE
        if (authCode.getCodeChallenge() != null) {
            if (codeVerifier == null) {
                throw new RuntimeException("缺少 code_verifier");
            }
            verifyCodeChallenge(authCode.getCodeChallenge(), authCode.getCodeChallengeMethod(), codeVerifier);
        }

        // 标记授权码为已使用
        authCode.setUsed(true);
        authorizationCodeRepository.save(authCode);

        User user = authCode.getUser();
        String scope = authCode.getScope();

        // 生成 Token
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("sub", user.getUsername());
        userInfo.put("name", user.getUsername());
        userInfo.put("email", user.getEmail());
        
        // ID Token
        String idToken = tokenService.generateIdToken(
                user.getUsername(), 
                clientId, 
                authCode.getNonce(), 
                userInfo
        );

        // Access Token
        String accessToken = tokenService.generateAccessToken(
                user.getUsername(),
                clientId,
                scope
        );

        // Refresh Token
        String refreshTokenValue = UUID.randomUUID().toString().replace("-", "");
        RefreshToken refreshToken = new RefreshToken(
                refreshTokenValue, 
                user,
                LocalDateTime.now().plusDays(7)
        );
        refreshTokenRepository.save(refreshToken);

        // 返回 Token
        Map<String, Object> result = new HashMap<>();
        result.put("access_token", accessToken);
        result.put("token_type", "Bearer");
        result.put("expires_in", 1800);
        result.put("id_token", idToken);
        result.put("refresh_token", refreshTokenValue);
        result.put("scope", scope);

        // 如果有 userinfo 请求，添加用户信息
        if (scope != null && scope.contains("openid")) {
            Map<String, Object> userInfoResponse = new HashMap<>();
            userInfoResponse.put("sub", user.getUsername());
            userInfoResponse.put("name", user.getUsername());
            userInfoResponse.put("email", user.getEmail());
            result.put("userinfo", userInfoResponse);
        }

        return result;
    }

    /**
     * 使用客户端凭证获取 Token（机机账户）
     */
    public Map<String, Object> clientCredentialsGrant(String clientId, String clientSecret, String scope) {
        OidcClient client = clientRepository.findByClientId(clientId)
                .orElseThrow(() -> new RuntimeException("客户端不存在"));

        if (!client.getEnabled()) {
            throw new RuntimeException("客户端已禁用");
        }

        if (!passwordEncoder.matches(clientSecret, client.getClientSecret())) {
            throw new RuntimeException("客户端密钥错误");
        }

        // 生成 Access Token
        String accessToken = tokenService.generateAccessToken(clientId, clientId, scope);

        Map<String, Object> result = new HashMap<>();
        result.put("access_token", accessToken);
        result.put("token_type", "Bearer");
        result.put("expires_in", 1800);
        result.put("scope", scope);

        return result;
    }

    /**
     * 使用 Refresh Token 刷新 Token
     */
    public Map<String, Object> refreshTokenGrant(String refreshTokenValue) {
        RefreshToken refreshToken = refreshTokenRepository.findByToken(refreshTokenValue)
                .orElseThrow(() -> new RuntimeException("Refresh Token 无效"));

        if (!refreshToken.isValid()) {
            throw new RuntimeException("Refresh Token 已过期或已撤销");
        }

        User user = refreshToken.getUser();

        // 撤销旧 Refresh Token
        refreshToken.setRevoked(true);
        refreshTokenRepository.save(refreshToken);

        // 生成新的 Token
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("sub", user.getUsername());
        userInfo.put("name", user.getUsername());
        userInfo.put("email", user.getEmail());

        String idToken = tokenService.generateIdToken(user.getUsername(), "refresh", null, userInfo);
        String accessToken = tokenService.generateAccessToken(user.getUsername(), "refresh", "openid profile email");

        String newRefreshTokenValue = UUID.randomUUID().toString().replace("-", "");
        RefreshToken newRefreshToken = new RefreshToken(newRefreshTokenValue, user, LocalDateTime.now().plusDays(7));
        refreshTokenRepository.save(newRefreshToken);

        Map<String, Object> result = new HashMap<>();
        result.put("access_token", accessToken);
        result.put("token_type", "Bearer");
        result.put("expires_in", 1800);
        result.put("id_token", idToken);
        result.put("refresh_token", newRefreshTokenValue);

        return result;
    }

    /**
     * 验证 PKCE code_challenge
     */
    private void verifyCodeChallenge(String codeChallenge, String method, String codeVerifier) {
        try {
            String challenge;
            if ("S256".equals(method)) {
                // SHA256 + Base64URL
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                byte[] hash = digest.digest(codeVerifier.getBytes(StandardCharsets.US_ASCII));
                challenge = Base64.getUrlEncoder().withoutPadding().encodeToString(hash);
            } else {
                // plain
                challenge = codeVerifier;
            }

            if (!challenge.equals(codeChallenge)) {
                throw new RuntimeException("code_verifier 不匹配");
            }
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("不支持的 PKCE 方法");
        }
    }

    /**
     * 获取用户信息
     */
    public Map<String, Object> getUserInfo(String accessToken) {
        String subject = tokenService.getSubjectFromToken(accessToken);
        
        User user = userRepository.findByUsername(subject)
                .orElseThrow(() -> new RuntimeException("用户不存在"));

        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("sub", user.getUsername());
        userInfo.put("name", user.getUsername());
        userInfo.put("email", user.getEmail());
        
        return userInfo;
    }
}
