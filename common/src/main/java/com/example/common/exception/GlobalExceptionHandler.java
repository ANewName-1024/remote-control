package com.example.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.BindException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.NoHandlerFoundException;

import java.util.stream.Collectors;

/**
 * 全局异常处理器
 * 
 * 统一处理所有异常，返回规范的响应格式
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger logger = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * 获取 Trace ID
     */
    private String getTraceId() {
        return MDC.get("traceId");
    }

    // ========== 业务异常 ==========

    /**
     * 业务异常处理
     */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<Void>> handleBusinessException(
            BusinessException e, HttpServletRequest request) {
        
        logger.warn("Business exception: code={}, message={}", e.getCode(), e.getMessage());
        
        ApiResponse<Void> response = ApiResponse.error(e.getCode(), e.getMessage());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.valueOf(e.getCode()))
                .body(response);
    }

    // ========== Spring Security 异常 ==========

    /**
     * 认证失败
     */
    @ExceptionHandler(AuthenticationException.class)
    public ResponseEntity<ApiResponse<Void>> handleAuthenticationException(
            AuthenticationException e, HttpServletRequest request) {
        
        logger.warn("Authentication failed: {}", e.getMessage());
        
        ApiResponse<Void> response = ApiResponse.unauthorized("认证失败: " + e.getMessage());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNAUTHORIZED)
                .body(response);
    }

    /**
     * 凭证错误
     */
    @ExceptionHandler(BadCredentialsException.class)
    public ResponseEntity<ApiResponse<Void>> handleBadCredentialsException(
            BadCredentialsException e, HttpServletRequest request) {
        
        logger.warn("Bad credentials: {}", e.getMessage());
        
        ApiResponse<Void> response = ApiResponse.unauthorized("用户名或密码错误");
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNAUTHORIZED)
                .body(response);
    }

    /**
     * 权限不足
     */
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiResponse<Void>> handleAccessDeniedException(
            AccessDeniedException e, HttpServletRequest request) {
        
        logger.warn("Access denied: {}", e.getMessage());
        
        ApiResponse<Void> response = ApiResponse.forbidden("权限不足");
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.FORBIDDEN)
                .body(response);
    }

    // ========== 参数校验异常 ==========

    /**
     * 请求体参数校验失败 (@Valid)
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<Void>> handleMethodArgumentNotValidException(
            MethodArgumentNotValidException e, HttpServletRequest request) {
        
        String errors = e.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .collect(Collectors.joining(", "));
        
        logger.warn("Validation failed: {}", errors);
        
        ApiResponse<Void> response = ApiResponse.validationError("参数校验失败: " + errors);
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(response);
    }

    /**
     * 表单参数校验失败 (@Valid)
     */
    @ExceptionHandler(BindException.class)
    public ResponseEntity<ApiResponse<Void>> handleBindException(
            BindException e, HttpServletRequest request) {
        
        String errors = e.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .collect(Collectors.joining(", "));
        
        logger.warn("Bind failed: {}", errors);
        
        ApiResponse<Void> response = ApiResponse.validationError("参数绑定失败: " + errors);
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(response);
    }

    /**
     * 单个参数校验失败
     */
    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiResponse<Void>> handleConstraintViolationException(
            ConstraintViolationException e, HttpServletRequest request) {
        
        String errors = e.getConstraintViolations().stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .collect(Collectors.joining(", "));
        
        logger.warn("Constraint violation: {}", errors);
        
        ApiResponse<Void> response = ApiResponse.validationError("参数约束违反: " + errors);
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(response);
    }

    // ========== 参数类型异常 ==========

    /**
     * 缺少参数
     */
    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiResponse<Void>> handleMissingParameterException(
            MissingServletRequestParameterException e, HttpServletRequest request) {
        
        logger.warn("Missing parameter: {}", e.getParameterName());
        
        ApiResponse<Void> response = ApiResponse.badRequest("缺少参数: " + e.getParameterName());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(response);
    }

    /**
     * 参数类型不匹配
     */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiResponse<Void>> handleTypeMismatchException(
            MethodArgumentTypeMismatchException e, HttpServletRequest request) {
        
        logger.warn("Type mismatch: {}", e.getName());
        
        ApiResponse<Void> response = ApiResponse.badRequest(
                "参数类型错误: " + e.getName() + ", 期望类型: " + e.getRequiredType());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(response);
    }

    // ========== HTTP 方法异常 ==========

    /**
     * 不支持的 HTTP 方法
     */
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> handleMethodNotSupportedException(
            HttpRequestMethodNotSupportedException e, HttpServletRequest request) {
        
        logger.warn("Method not supported: {}", e.getMethod());
        
        ApiResponse<Void> response = ApiResponse.badRequest(
                "不支持的 HTTP 方法: " + e.getMethod());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.METHOD_NOT_ALLOWED)
                .body(response);
    }

    /**
     * 不支持的媒体类型
     */
    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> handleMediaTypeNotSupportedException(
            HttpMediaTypeNotSupportedException e, HttpServletRequest request) {
        
        logger.warn("Media type not supported: {}", e.getContentType());
        
        ApiResponse<Void> response = ApiResponse.badRequest(
                "不支持的媒体类型: " + e.getContentType());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)
                .body(response);
    }

    // ========== 404 异常 ==========

    /**
     * 找不到处理器
     */
    @ExceptionHandler(NoHandlerFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNoHandlerFoundException(
            NoHandlerFoundException e, HttpServletRequest request) {
        
        logger.warn("No handler found: {}", e.getRequestURL());
        
        ApiResponse<Void> response = ApiResponse.notFound("接口不存在: " + e.getRequestURL());
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(response);
    }

    // ========== 其他异常 ==========

    /**
     * 其他所有异常
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleException(
            Exception e, HttpServletRequest request) {
        
        logger.error("Unhandled exception", e);
        
        ApiResponse<Void> response = ApiResponse.internalError(
                "服务器内部错误，请稍后重试");
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(response);
    }

    /**
     * Throwable (包括 Error)
     */
    @ExceptionHandler(Throwable.class)
    public ResponseEntity<ApiResponse<Void>> handleThrowable(
            Throwable e, HttpServletRequest request) {
        
        logger.error("Unhandled throwable", e);
        
        ApiResponse<Void> response = ApiResponse.serviceUnavailable(
                "服务暂时不可用，请稍后重试");
        response.setTraceId(getTraceId());
        
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(response);
    }
}
