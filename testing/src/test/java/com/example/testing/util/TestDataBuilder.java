package com.example.testing.util;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.UUID;

/**
 * 测试数据构建工具
 */
public class TestDataBuilder {

    private static final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    // ==================== 通用测试数据 ====================

    /**
     * 生成随机字符串
     */
    public static String randomString(int length) {
        return UUID.randomUUID().toString().replace("-", "").substring(0, length);
    }

    /**
     * 生成随机邮箱
     */
    public static String randomEmail() {
        return "test_" + randomString(8) + "@example.com";
    }

    /**
     * 生成随机用户名
     */
    public static String randomUsername() {
        return "user_" + randomString(8);
    }

    /**
     * 生成随机手机号
     */
    public static String randomPhone() {
        return "1" + (int) (Math.random() * 9 + 1) + String.format("%09d", (int) (Math.random() * 1000000000));
    }

    // ==================== 用户测试数据 ====================

    /**
     * 创建测试用户
     */
    public static UserBuilder user() {
        return new UserBuilder();
    }

    public static class UserBuilder {
        private String username = randomUsername();
        private String email = randomEmail();
        private String password = "Test@123456";
        private boolean enabled = true;

        public UserBuilder username(String username) {
            this.username = username;
            return this;
        }

        public UserBuilder email(String email) {
            this.email = email;
            return this;
        }

        public UserBuilder password(String password) {
            this.password = password;
            return this;
        }

        public UserBuilder enabled(boolean enabled) {
            this.enabled = enabled;
            return this;
        }

        public com.example.user.entity.User build() {
            com.example.user.entity.User user = new com.example.user.entity.User();
            user.setUsername(username);
            user.setEmail(email);
            user.setPassword(password);
            user.setEnabled(enabled);
            user.setCreatedAt(LocalDateTime.now());
            user.setUpdatedAt(LocalDateTime.now());
            return user;
        }
    }

    // ==================== JSON 工具 ====================

    /**
     * 对象转 JSON
     */
    public static String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (IOException e) {
            throw new RuntimeException("JSON 序列化失败", e);
        }
    }

    /**
     * JSON 转对象
     */
    public static <T> T fromJson(String json, Class<T> clazz) {
        try {
            return objectMapper.readValue(json, clazz);
        } catch (IOException e) {
            throw new RuntimeException("JSON 反序列化失败", e);
        }
    }

    /**
     * 创建分页请求参数
     */
    public static String createPageRequest(int page, int size) {
        return String.format("{\"page\":%d,\"size\":%d}", page, size);
    }

    /**
     * 创建排序请求参数
     */
    public static String createSortRequest(String field, String direction) {
        return String.format("{\"sort\":\"%s\",\"direction\":\"%s\"}", field, direction);
    }
}
