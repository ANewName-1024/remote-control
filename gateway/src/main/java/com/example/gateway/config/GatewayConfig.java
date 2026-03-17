package com.example.gateway.config;

import com.example.gateway.filter.OidcAuthenticationFilter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Gateway 路由配置
 */
@Configuration
public class GatewayConfig {

    @Autowired
    private OidcAuthenticationFilter oidcAuthenticationFilter;

    @Bean
    public RouteLocator customRouteLocator(RouteLocatorBuilder builder) {
        return builder.routes()
                // 动态路由由 Spring Cloud Gateway 自动发现
                .build();
    }
}
