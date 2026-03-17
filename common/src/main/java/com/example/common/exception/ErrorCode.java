package com.example.common.exception;

/**
 * 业务错误码枚举
 * 
 * 错误码规则:
 * - 1xxxx: 通用错误
 * - 2xxxx: 认证/授权错误
 * - 3xxxx: 用户相关错误
 * - 4xxxx: 资源相关错误
 * - 5xxxx: 配置相关错误
 */
public enum ErrorCode {

    // ========== 1xxxx: 通用错误 ==========
    SUCCESS(200, "成功"),
    BAD_REQUEST(400, "请求参数错误"),
    INVALID_PARAMETER(400, "无效参数"),
    VALIDATION_FAILED(422, "参数校验失败"),
    
    // ========== 2xxxx: 认证/授权错误 ==========
    UNAUTHORIZED(401, "未登录"),
    TOKEN_EXPIRED(401, "Token 已过期"),
    TOKEN_INVALID(401, "无效的 Token"),
    FORBIDDEN(403, "权限不足"),
    ACCESS_DENIED(403, "拒绝访问"),
    
    // ========== 3xxxx: 用户相关错误 ==========
    USER_NOT_FOUND(404, "用户不存在"),
    USER_ALREADY_EXISTS(409, "用户已存在"),
    USERNAME_EXISTS(409, "用户名已存在"),
    EMAIL_EXISTS(409, "邮箱已被注册"),
    PASSWORD_INCORRECT(401, "密码错误"),
    PASSWORD_WEAK(400, "密码强度不足"),
    ACCOUNT_DISABLED(403, "账号已被禁用"),
    ACCOUNT_LOCKED(403, "账号已被锁定"),
    
    // ========== 4xxxx: 资源相关错误 ==========
    RESOURCE_NOT_FOUND(404, "资源不存在"),
    RESOURCE_ALREADY_EXISTS(409, "资源已存在"),
    RESOURCE_CONFLICT(409, "资源冲突"),
    
    // ========== 5xxxx: 配置相关错误 ==========
    CONFIG_NOT_FOUND(404, "配置不存在"),
    CONFIG_INVALID(400, "配置无效"),
    ENCRYPTION_FAILED(500, "加密失败"),
    DECRYPTION_FAILED(500, "解密失败"),
    
    // ========== 系统错误 ==========
    INTERNAL_ERROR(500, "服务器内部错误"),
    SERVICE_UNAVAILABLE(503, "服务不可用"),
    DATABASE_ERROR(500, "数据库错误"),
    NETWORK_ERROR(500, "网络错误"),
    TIMEOUT(504, "请求超时");

    private final int code;
    private final String message;

    ErrorCode(int code, String message) {
        this.code = code;
        this.message = message;
    }

    public int getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }

    /**
     * 创建业务异常
     */
    public BusinessException exception() {
        return new BusinessException(code, message);
    }

    /**
     * 创建业务异常 (自定义消息)
     */
    public BusinessException exception(String customMessage) {
        return new BusinessException(code, customMessage);
    }
}
