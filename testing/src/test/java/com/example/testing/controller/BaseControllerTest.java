package com.example.testing.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Controller 基础测试类
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class BaseControllerTest {

    @Autowired
    protected MockMvc mockMvc;

    /**
     * GET 请求
     */
    protected ResultActions get(String url) throws Exception {
        return mockMvc.perform(get(url));
    }

    /**
     * POST 请求
     */
    protected ResultActions post(String url) throws Exception {
        return mockMvc.perform(post(url));
    }

    /**
     * POST JSON 请求
     */
    protected ResultActions postJson(String url, String json) throws Exception {
        return mockMvc.perform(post(url)
                .contentType(MediaType.APPLICATION_JSON)
                .content(json));
    }

    /**
     * PUT 请求
     */
    protected ResultActions put(String url) throws Exception {
        return mockMvc.perform(put(url));
    }

    /**
     * PUT JSON 请求
     */
    protected ResultActions putJson(String url, String json) throws Exception {
        return mockMvc.perform(put(url)
                .contentType(MediaType.APPLICATION_JSON)
                .content(json));
    }

    /**
     * DELETE 请求
     */
    protected ResultActions delete(String url) throws Exception {
        return mockMvc.perform(delete(url));
    }

    /**
     * 验证成功响应
     */
    protected ResultActions expectSuccess(ResultActions result) throws Exception {
        return result.andExpect(status().isOk());
    }

    /**
     * 验证失败响应
     */
    protected ResultActions expectError(ResultActions result, int status) throws Exception {
        return result.andExpect(status().is(status));
    }

    /**
     * 验证响应包含字段
     */
    protected ResultActions expectHasField(ResultActions result, String field) throws Exception {
        return result.andExpect(jsonPath(field).exists());
    }
}
