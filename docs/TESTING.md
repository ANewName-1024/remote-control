# 测试指南

## 概述

本文档描述项目的测试策略、测试框架和最佳实践。

## 测试金字塔

```
           /\
          /  \
         / E2E \        E2E 测试 (10%)
        /--------\
       /  集成   \      集成测试 (20%)
      /------------\
     /   单元测试   \    单元测试 (70%)
    /________________\
```

## 测试模块

### testing 模块结构

```
testing/
├── pom.xml
└── src/test/
    ├── java/com/example/testing/
    │   ├── BaseSpringBootTest.java      # Spring Boot 基础测试
    │   ├── controller/
    │   │   └── BaseControllerTest.java   # Controller 测试基类
    │   ├── service/
    │   │   └── BaseServiceTest.java      # Service 测试基类
    │   ├── util/
    │   │   └── TestDataBuilder.java      # 测试数据构建工具
    │   └── security/
    │       └── TestJwtUtil.java          # JWT 测试工具
    └── resources/
        └── application-test.yml          # 测试配置
```

## 单元测试

### Service 层测试

```java
@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock
    private UserRepository userRepository;
    
    @InjectMocks
    private UserService userService;

    @Test
    void shouldCreateUser() {
        // Given
        User user = new User();
        user.setUsername("test");
        when(userRepository.save(any(User.class))).thenReturn(user);

        // When
        User result = userService.createUser(user);

        // Then
        assertThat(result.getUsername()).isEqualTo("test");
    }
}
```

### 使用基类

```java
class UserServiceTest extends BaseServiceTest<User, Long> {

    @Override
    protected User createEntity() {
        User user = new User();
        user.setUsername("test");
        return user;
    }

    @Override
    protected Long getEntityId(User entity) {
        return entity.getId();
    }
}
```

## 集成测试

### Controller 测试

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldGetUser() throws Exception {
        mockMvc.perform(get("/user/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").exists());
    }
}
```

### 使用基类

```java
class AuthControllerTest extends BaseControllerTest {

    @Test
    void shouldLogin() throws Exception {
        String requestBody = TestDataBuilder.toJson(
            Map.of("username", "test", "password", "Test@123")
        );
        
        postJson("/user/auth/login", requestBody)
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accessToken").exists());
    }
}
```

## 安全测试

### 认证测试

```java
@Test
void shouldDenyAccessWithoutToken() throws Exception {
    mockMvc.perform(get("/user/profile"))
            .andExpect(status().isUnauthorized());
}

@Test
void shouldAllowAccessWithToken() throws Exception {
    String token = TestJwtUtil.generateUserToken();
    
    mockMvc.perform(get("/user/profile")
            .header("Authorization", TestJwtUtil.authHeader(token)))
            .andExpect(status().isOk());
}
```

### 权限测试

```java
@Test
void shouldDenyAdminEndpointForNormalUser() throws Exception {
    String token = TestJwtUtil.generateUserToken();
    
    mockMvc.perform(get("/user/admin/users")
            .header("Authorization", TestJwtUtil.authHeader(token)))
            .andExpect(status().isForbidden());
}

@Test
void shouldAllowAdminEndpointForAdmin() throws Exception {
    String token = TestJwtUtil.generateAdminToken();
    
    mockMvc.perform(get("/user/admin/users")
            .header("Authorization", TestJwtUtil.authHeader(token)))
            .andExpect(status().isOk());
}
```

## 测试数据

### 使用 TestDataBuilder

```java
// 创建用户
User user = TestDataBuilder.user()
    .username("testuser")
    .email("test@example.com")
    .password("Test@123")
    .enabled(true)
    .build();

// 创建随机用户
User randomUser = TestDataBuilder.user().build();

// 生成随机字符串
String randomStr = TestDataBuilder.randomString(16);

// 生成随机邮箱
String randomEmail = TestDataBuilder.randomEmail();
```

## 测试配置

### application-test.yml

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb
    driver-class-name: org.h2.Driver
  jpa:
    hibernate:
      ddl-auto: create-drop
```

## 运行测试

```bash
# 运行所有测试
mvn test

# 运行单元测试
mvn test -Dtest=*ServiceTest

# 运行集成测试
mvn test -Dtest=*ControllerTest

# 生成覆盖率报告
mvn test jacoco:report
```

## 测试覆盖目标

| 层级 | 目标覆盖率 |
|------|-----------|
| Service | >= 80% |
| Controller | >= 70% |
| Overall | >= 60% |

## 最佳实践

### 测试命名

```java
// ✅ 好的命名
class UserServiceTest {
    @Test
    void shouldReturnUserWhenIdExists() {}
    
    @Test
    void shouldThrowExceptionWhenUserNotFound() {}
    
    @Test
    void shouldEncryptPasswordBeforeSave() {}
}

// ❌ 差的命名
class UserServiceTest {
    @Test
    void test1() {}
    
    @Test
    void testCreate() {}
}
```

### AAA 模式

```java
@Test
void shouldDoSomething() {
    // Arrange - 准备
    User user = new User();
    
    // Act - 执行
    User result = service.process(user);
    
    // Assert - 断言
    assertThat(result).isNotNull();
}
```

### 测试隔离

```java
@BeforeEach
void setUp() {
    MockitoAnnotations.openMocks(this);
    repository.deleteAll(); // 每个测试前清理数据
}
```

### Mock 原则

```java
// ✅ 正确 - Mock 外部依赖
@Mock
private UserRepository userRepository;

// ❌ 错误 - 不要 Mock 被测试的类
// @InjectMocks
// private UserService userService; // 这是错的
```

## CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up JDK
        uses: actions/setup-java@v3
        with:
          java-version: '17'
      - name: Run tests
        run: mvn test
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

最后更新: 2026-03-17
