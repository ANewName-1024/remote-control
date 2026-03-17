# 全局异常处理设计

## 概述

本文档定义 Spring Cloud Demo 项目的全局异常处理机制，确保所有 API 响应格式统一、错误处理规范。

## 架构设计

### 异常分类

```
异常体系
├── BusinessException (业务异常)
│   ├── 认证异常 (AuthenticationException)
│   ├── 权限异常 (AccessDeniedException)
│   └── 自定义业务异常
├── ValidationException (参数校验异常)
│   ├── MethodArgumentNotValidException
│   ├── BindException
│   └── ConstraintViolationException
└── SystemException (系统异常)
    ├── DatabaseException
    ├── NetworkException
    └── ThirdPartyException
```

### 处理流程

```
请求进入
    │
    ▼
┌─────────────────┐
│  Controller     │
│  处理请求        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Service        │ ──▶ 正常 ──▶ 返回结果
│  业务处理       │
└────────┬────────┘
         │ 抛出异常
         ▼
┌─────────────────┐
│ ExceptionHandler│
│ 全局异常处理     │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
业务异常    系统异常
    │         │
    ▼         ▼
记录日志    记录日志
返回业务错误  返回通用错误
```

## 统一响应格式

### 成功响应

```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "id": 1,
    "username": "admin"
  },
  "traceId": "abc123",
  "timestamp": "2026-03-17T16:00:00Z"
}
```

### 错误响应

```json
{
  "code": 404,
  "message": "用户不存在",
  "data": null,
  "traceId": "abc123",
  "timestamp": "2026-03-17T16:00:00Z"
}
```

## 状态码规范

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 无内容 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 参数校验失败 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

### 业务错误码

| 错误码 | 说明 |
|--------|------|
| 1xxxx | 通用错误 |
| 2xxxx | 认证/授权错误 |
| 3xxxx | 用户相关错误 |
| 4xxxx | 资源相关错误 |
| 5xxxx | 配置相关错误 |

## 异常处理策略

### 1. 业务异常 (BusinessException)

```java
// 抛出业务异常
throw BusinessException.notFound("用户不存在");
throw BusinessException.unauthorized("Token 已过期");
throw BusinessException.forbidden("权限不足");
```

### 2. 参数校验异常

```java
// 使用 @Valid 注解自动校验
@PostMapping("/user")
public ApiResponse<User> createUser(@Valid @RequestBody UserDTO dto) {
    // ...
}
```

### 3. 认证异常

```java
// Spring Security 自动处理
// 可自定义 AuthenticationEntryPoint
```

### 4. 系统异常

```java
// 自动捕获，返回通用错误
// 记录详细日志
// 不暴露内部信息给客户端
```

## 日志规范

### 异常日志级别

| 异常类型 | 日志级别 | 记录内容 |
|----------|----------|----------|
| 业务异常 | WARN | 错误码、消息 |
| 认证异常 | WARN | 用户、原因 |
| 参数异常 | INFO | 参数、错误信息 |
| 系统异常 | ERROR | 完整堆栈 |

### 日志格式

```json
{
  "timestamp": "2026-03-17T16:00:00.000",
  "level": "ERROR",
  "logger": "GlobalExceptionHandler",
  "message": "Unhandled exception",
  "traceId": "abc123",
  "exception": {
    "class": "NullPointerException",
    "message": "Cannot read property 'id' of null",
    "stackTrace": "..."
  }
}
```

## 分布式追踪

### Trace ID 传递

1. Gateway 生成 Trace ID
2. 通过 Header 传递给下游服务
3. 异常响应中包含 Trace ID
4. 日志中记录 Trace ID

### Header 规范

| Header | 说明 |
|--------|------|
| X-Trace-ID | 链路追踪 ID |
| X-Request-ID | 请求 ID |
| X-Correlation-ID | 关联 ID |

## 配置示例

### application.yml

```yaml
# 异常处理配置
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never

# 自定义错误路径
spring:
  mvc:
    throw-exception-if-no-handler-found: true
  web:
    resources:
      add-mappings: false
```

### 使用示例

```java
// 1. 抛出业务异常
@PostMapping("/users")
public ApiResponse<User> createUser(@Valid @RequestBody CreateUserRequest request) {
    if (userRepository.existsByUsername(request.getUsername())) {
        throw ErrorCode.USER_ALREADY_EXISTS.exception("用户名已存在");
    }
    // ...
}

// 2. 使用枚举错误码
@PostMapping("/login")
public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
    User user = authService.login(request);
    if (user == null) {
        throw ErrorCode.PASSWORD_INCORRECT.exception();
    }
    return ApiResponse.success(user);
}
```

## 最佳实践

1. **不暴露内部异常**: 系统异常只返回通用消息
2. **记录完整日志**: 包含堆栈、参数、上下文
3. **统一错误格式**: 所有响应使用相同结构
4. **国际化支持**: 错误消息支持多语言
5. **监控告警**: 异常自动告警
6. **错误码追溯**: 通过错误码快速定位问题

---

最后更新: 2026-03-17
