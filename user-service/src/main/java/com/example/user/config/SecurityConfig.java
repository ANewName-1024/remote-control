package com.example.user.config;

import com.example.user.security.JwtAuthenticationFilter;
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
 * Spring Security 配置
 * Gateway 统一认证后，各服务信任 Gateway 传递的请求头
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

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
                .requestMatchers("/user/auth/login", "/user/auth/register").permitAll()
                // 健康检查
                .requestMatchers("/actuator/**", "/health").permitAll()
                // 需要 admin 权限
                .requestMatchers("/user/admin/**").hasAuthority("admin:manage")
                // 其他接口需要认证（Gateway 已验证）
                .requestMatchers("/user/**").authenticated()
                .anyRequest().permitAll()
            );

        return http.build();
    }
}
