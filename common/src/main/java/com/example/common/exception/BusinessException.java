package com.example.common.exception;

/**
 * 业务异常基类
 * 
 * 所有业务异常继承此异常
 */
public class BusinessException extends RuntimeException {

    /**
     * 错误码
     */
    private int code;

    /**
     * 错误消息
     */
    private String message;

    /**
     * 详细信息 (用于调试)
     */
    private String details;

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
        this.message = message;
    }

    public BusinessException(int code, String message, String details) {
        super(message);
        this.code = code;
        this.message = message;
        this.details = details;
    }

    public BusinessException(int code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
        this.message = message;
    }

    // ========== 常用静态工厂 ==========

    /**
     * 400 Bad Request
     */
    public static BusinessException badRequest(String message) {
        return new BusinessException(400, message);
    }

    /**
     * 401 Unauthorized
     */
    public static BusinessException unauthorized(String message) {
        return new BusinessException(401, message);
    }

    /**
     * 403 Forbidden
     */
    public static BusinessException forbidden(String message) {
        return new BusinessException(403, message);
    }

    /**
     * 404 Not Found
     */
    public static BusinessException notFound(String message) {
        return new BusinessException(404, message);
    }

    /**
     * 409 Conflict
     */
    public static BusinessException conflict(String message) {
        return new BusinessException(409, message);
    }

    /**
     * 500 Internal Error
     */
    public static BusinessException internalError(String message) {
        return new BusinessException(500, message);
    }

    // ========== Getters and Setters ==========

    public int getCode() { return code; }
    public void setCode(int code) { this.code = code; }

    @Override
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public String getDetails() { return details; }
    public void setDetails(String details) { this.details = details; }
}
