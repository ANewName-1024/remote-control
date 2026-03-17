package com.example.common.exception;

import com.fasterxml.jackson.annotation.JsonInclude;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;

/**
 * 全局统一响应
 * 
 * 所有 API 响应统一使用此格式
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ApiResponse<T> {

    private static final Logger logger = LoggerFactory.getLogger(ApiResponse.class);

    /**
     * 响应状态码
     */
    private int code;

    /**
     * 响应消息
     */
    private String message;

    /**
     * 响应数据
     */
    private T data;

    /**
     * 请求追踪 ID (用于日志定位)
     */
    private String traceId;

    /**
     * 时间戳
     */
    private Instant timestamp;

    // 成功状态码
    public static final int CODE_SUCCESS = 200;
    public static final int CODE_CREATED = 201;
    public static final int CODE_NO_CONTENT = 204;

    // 客户端错误状态码
    public static final int CODE_BAD_REQUEST = 400;
    public static final int CODE_UNAUTHORIZED = 401;
    public static final int CODE_FORBIDDEN = 403;
    public static final int CODE_NOT_FOUND = 404;
    public static final int CODE_CONFLICT = 409;
    public static final int CODE_VALIDATION_ERROR = 422;

    // 服务端错误状态码
    public static final int CODE_INTERNAL_ERROR = 500;
    public static final int CODE_SERVICE_UNAVAILABLE = 503;

    // 私有构造方法
    private ApiResponse() {
        this.timestamp = Instant.now();
    }

    // ========== 静态工厂方法 ==========

    /**
     * 成功响应
     */
    public static <T> ApiResponse<T> success() {
        return success(null);
    }

    /**
     * 成功响应 (带数据)
     */
    public static <T> ApiResponse<T> success(T data) {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = CODE_SUCCESS;
        response.message = "Success";
        response.data = data;
        return response;
    }

    /**
     * 成功响应 (带消息和数据)
     */
    public static <T> ApiResponse<T> success(String message, T data) {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = CODE_SUCCESS;
        response.message = message;
        response.data = data;
        return response;
    }

    /**
     * 创建响应 (带自定义状态码)
     */
    public static <T> ApiResponse<T> of(int code, String message, T data) {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = code;
        response.message = message;
        response.data = data;
        return response;
    }

    /**
     * 201 Created
     */
    public static <T> ApiResponse<T> created(T data) {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = CODE_CREATED;
        response.message = "Created successfully";
        response.data = data;
        return response;
    }

    /**
     * 204 No Content
     */
    public static <T> ApiResponse<T> noContent() {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = CODE_NO_CONTENT;
        response.message = "No content";
        return response;
    }

    // ========== 错误响应 ==========

    /**
     * 400 Bad Request
     */
    public static <T> ApiResponse<T> badRequest(String message) {
        return error(CODE_BAD_REQUEST, message);
    }

    /**
     * 401 Unauthorized
     */
    public static <T> ApiResponse<T> unauthorized(String message) {
        return error(CODE_UNAUTHORIZED, message);
    }

    /**
     * 403 Forbidden
     */
    public static <T> ApiResponse<T> forbidden(String message) {
        return error(CODE_FORBIDDEN, message);
    }

    /**
     * 404 Not Found
     */
    public static <T> ApiResponse<T> notFound(String message) {
        return error(CODE_NOT_FOUND, message);
    }

    /**
     * 409 Conflict
     */
    public static <T> ApiResponse<T> conflict(String message) {
        return error(CODE_CONFLICT, message);
    }

    /**
     * 422 Validation Error
     */
    public static <T> ApiResponse<T> validationError(String message) {
        return error(CODE_VALIDATION_ERROR, message);
    }

    /**
     * 500 Internal Server Error
     */
    public static <T> ApiResponse<T> internalError(String message) {
        return error(CODE_INTERNAL_ERROR, message);
    }

    /**
     * 503 Service Unavailable
     */
    public static <T> ApiResponse<T> serviceUnavailable(String message) {
        return error(CODE_SERVICE_UNAVAILABLE, message);
    }

    /**
     * 自定义错误
     */
    public static <T> ApiResponse<T> error(int code, String message) {
        ApiResponse<T> response = new ApiResponse<>();
        response.code = code;
        response.message = message;
        return response;
    }

    // ========== 异常转换 ==========

    /**
     * 从异常创建错误响应
     */
    public static <T> ApiResponse<T> fromException(BusinessException e) {
        return error(e.getCode(), e.getMessage());
    }

    public static <T> ApiResponse<T> fromException(Throwable e) {
        logger.error("Unhandled exception", e);
        return internalError(e.getMessage());
    }

    // ========== Getters and Setters ==========

    public int getCode() { return code; }
    public void setCode(int code) { this.code = code; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public T getData() { return data; }
    public void setData(T data) { this.data = data; }

    public String getTraceId() { return traceId; }
    public void setTraceId(String traceId) { this.traceId = traceId; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }

    // ========== 辅助方法 ==========

    /**
     * 判断是否成功
     */
    public boolean isSuccess() {
        return code >= 200 && code < 300;
    }

    /**
     * 判断是否有错误
     */
    public boolean isError() {
        return code >= 400;
    }

    @Override
    public String toString() {
        return "ApiResponse{" +
                "code=" + code +
                ", message='" + message + '\'' +
                ", data=" + data +
                ", traceId='" + traceId + '\'' +
                ", timestamp=" + timestamp +
                '}';
    }
}
