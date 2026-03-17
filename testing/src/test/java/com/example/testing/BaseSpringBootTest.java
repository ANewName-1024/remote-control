package com.example.testing;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Spring Boot 基础测试
 */
@SpringBootTest
@ActiveProfiles("test")
public abstract class BaseSpringBootTest {

    @Test
    @DisplayName("测试上下文加载")
    void contextLoads() {
        assertThat(true).isTrue();
    }
}
