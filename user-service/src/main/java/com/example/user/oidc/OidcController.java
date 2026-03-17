package com.example.user.oidc;

import com.example.user.entity.OidcClient;
import com.example.user.repository.OidcClientRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.*;

/**
 * OIDC / OAuth 2.0 授权控制器
 */
@RestController
@RequestMapping("/oauth")
public class OidcController {

    @Autowired
    private OidcAuthorizationService authorizationService;

    @Autowired
    private OidcTokenService tokenService;

    @Autowired
    private OidcClientRepository clientRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Value("${oidc.issuer:http://localhost:8081}")
    private String issuer;

    // ==================== OIDC 发现文档 ====================

    /**
     * OIDC 发现文档
     */
    @GetMapping("/.well-known/openid-configuration")
    public ResponseEntity<Map<String, Object>> getDiscoveryDocument() {
        return ResponseEntity.ok(tokenService.getDiscoveryDocument());
    }

    /**
     * JWKS
     */
    @GetMapping("/jwks")
    public ResponseEntity<Map<String, Object>> getJwks() {
        return ResponseEntity.ok(tokenService.getJwks());
    }

    // ==================== 授权端点 ====================

    /**
     * 授权端点
     * GET /oauth/authorize?response_type=code&client_id=xxx&redirect_uri=xxx&scope=openid&state=xxx
     */
    @GetMapping("/authorize")
    public ResponseEntity<?> authorize(
            @RequestParam String response_type,
            @RequestParam String client_id,
            @RequestParam String redirect_uri,
            @RequestParam(required = false) String scope,
            @RequestParam(required = false) String state,
            @RequestParam(required = false) String nonce,
            @RequestParam(required = false) String code_challenge,
            @RequestParam(required = false) String code_challenge_method,
            @RequestParam(required = false) String user) {

        try {
            // 验证客户端
            authorizationService.validateClient(client_id, redirect_uri);

            // 生成授权码
            String code = authorizationService.generateAuthorizationCode(
                    client_id, redirect_uri, user, scope, nonce, state, 
                    code_challenge, code_challenge_method
            );

            // 返回授权码
            Map<String, Object> result = new HashMap<>();
            result.put("code", code);
            if (state != null) {
                result.put("state", state);
            }

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ==================== Token 端点 ====================

    /**
     * Token 端点
     * 支持 authorization_code, client_credentials, refresh_token, password
     */
    @PostMapping("/token")
    public ResponseEntity<?> token(@RequestParam Map<String, String> params) {
        try {
            String grantType = params.get("grant_type");

            Map<String, Object> result;

            switch (grantType) {
                case "authorization_code":
                    result = authorizationService.exchangeCodeForTokens(
                            params.get("code"),
                            params.get("client_id"),
                            params.get("client_secret"),
                            params.get("redirect_uri"),
                            params.get("code_verifier")
                    );
                    break;

                case "client_credentials":
                    result = authorizationService.clientCredentialsGrant(
                            params.get("client_id"),
                            params.get("client_secret"),
                            params.get("scope")
                    );
                    break;

                case "refresh_token":
                    result = authorizationService.refreshTokenGrant(
                            params.get("refresh_token")
                    );
                    break;

                case "password":
                    // 直接密码模式（仅用于信任客户端）
                    result = passwordGrant(
                            params.get("client_id"),
                            params.get("client_secret"),
                            params.get("username"),
                            params.get("password"),
                            params.get("scope")
                    );
                    break;

                default:
                    return ResponseEntity.badRequest()
                            .body(Map.of("error", "unsupported_grant_type"));
            }

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", e.getMessage()));
        }
    }

    // ==================== UserInfo 端点 ====================

    /**
     * UserInfo 端点
     */
    @GetMapping("/userinfo")
    public ResponseEntity<?> getUserInfo(@RequestHeader("Authorization") String authHeader) {
        try {
            String token = authHeader.substring(7);
            Map<String, Object> userInfo = authorizationService.getUserInfo(token);
            return ResponseEntity.ok(userInfo);
        } catch (Exception e) {
            return ResponseEntity.status(401).body(Map.of("error", e.getMessage()));
        }
    }

    /**
     * UserInfo 端点 (POST)
     */
    @PostMapping("/userinfo")
    public ResponseEntity<?> postUserInfo(@RequestHeader("Authorization") String authHeader) {
        return getUserInfo(authHeader);
    }

    // ==================== 客户端管理 ====================

    /**
     * 注册客户端
     */
    @PostMapping("/client/register")
    public ResponseEntity<?> registerClient(@RequestBody Map<String, Object> request) {
        try {
            String clientId = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
            String clientSecret = UUID.randomUUID().toString().replace("-", "");

            OidcClient client = new OidcClient();
            client.setClientId(clientId);
            client.setClientSecret(passwordEncoder.encode(clientSecret));
            client.setClientName((String) request.get("client_name"));
            client.setClientUri((String) request.get("client_uri"));
            client.setRedirectUris((String) request.get("redirect_uris"));
            client.setGrantTypes((String) request.getOrDefault("grant_types", "authorization_code,refresh_token"));
            client.setResponseTypes((String) request.getOrDefault("response_types", "code"));
            client.setScope((String) request.getOrDefault("scope", "openid profile email"));
            client.setTokenEndpointAuthMethod((String) request.getOrDefault("token_endpoint_auth_method", "client_secret_basic"));
            client.setEnabled(true);
            client.setCreatedAt(LocalDateTime.now());

            clientRepository.save(client);

            Map<String, Object> result = new HashMap<>();
            result.put("client_id", clientId);
            result.put("client_secret", clientSecret);
            result.put("client_id_issued_at", System.currentTimeMillis() / 1000);

            return ResponseEntity.ok(result);
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    // ==================== 密码模式 ====================

    private Map<String, Object> passwordGrant(String clientId, String clientSecret, 
                                            String username, String password, String scope) {
        // 验证客户端
        authorizationService.validateClient(clientId, "http://localhost");

        // 验证用户（使用 AuthService）
        // 这里简化处理，直接使用 tokenService
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("sub", username);
        userInfo.put("name", username);

        String accessToken = tokenService.generateAccessToken(username, clientId, scope);
        String idToken = tokenService.generateIdToken(username, clientId, null, userInfo);

        Map<String, Object> result = new HashMap<>();
        result.put("access_token", accessToken);
        result.put("token_type", "Bearer");
        result.put("expires_in", 1800);
        result.put("id_token", idToken);
        result.put("scope", scope);

        return result;
    }
}
