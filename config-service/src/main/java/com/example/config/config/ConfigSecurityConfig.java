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
 * Gateway 统一认证后，各服务信任 Gateway 传递的请求头
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
                // 认证接口公开
                .requestMatchers("/config/auth/login", "/config/auth/register").permitAll()
                // 健康检查
                .requestMatchers("/actuator/**", "/health").permitAll()
                // OpenClaw 配置需登录
                .requestMatchers("/openclaw/config/type/**").authenticated()
                // 管理接口需要用户权限
                .requestMatchers("/openclaw/config/**").hasRole("USER")
                .requestMatchers("/openclaw/key/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            );

        return http.build();
    }
}
