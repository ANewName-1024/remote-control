package com.example.config.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * 配置服务安全配置
 * 统一由 Gateway 进行 OIDC 认证
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ConfigSecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. 健康检查公开
                .requestMatchers("/actuator/**", "/health").permitAll()
                
                // 2. Spring Cloud Config 端点（建议通过 Gateway 访问）
                .requestMatchers("/**").permitAll()
                
                // 3. OpenClaw 配置需登录
                .requestMatchers("/openclaw/config/type/**").authenticated()
                
                // 4. 管理接口需要管理员权限
                .requestMatchers("/openclaw/config/**").hasRole("USER")
                .requestMatchers("/openclaw/key/**").hasRole("ADMIN")
                
                // 5. 其他请求需要认证
                .anyRequest().authenticated()
            )
            .headers(headers -> headers.frameOptions(frame -> frame.sameOrigin()));

        return http.build();
    }
}
