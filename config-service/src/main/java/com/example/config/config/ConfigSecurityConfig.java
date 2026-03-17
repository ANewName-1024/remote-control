package com.example.config.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
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
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. 认证接口公开 (Gateway 会放行)
                .requestMatchers("/config/auth/login", "/config/auth/register").permitAll()
                
                // 2. 健康检查公开
                .requestMatchers("/actuator/**", "/health").permitAll()
                
                // 3. Spring Cloud Config 端点 - 生产环境应通过 Gateway 访问
                .requestMatchers("/encrypt", "/encrypt/**").hasRole("ADMIN")
                .requestMatchers("/decrypt", "/decrypt/**").hasRole("ADMIN")
                .requestMatchers("/**").permitAll()  // Config 端点默认公开（建议通过 Gateway 保护）
                
                // 4. OpenClaw 配置需登录
                .requestMatchers("/openclaw/config/type/**").authenticated()
                
                // 5. 管理接口需要管理员权限
                .requestMatchers("/openclaw/config/**").hasRole("USER")
                .requestMatchers("/openclaw/key/**").hasRole("ADMIN")
                
                // 6. 其他请求需要认证
                .anyRequest().authenticated()
            )
            .headers(headers -> headers.frameOptions(frame -> frame.sameOrigin()));

        return http.build();
    }
}
