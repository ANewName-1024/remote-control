# Nacos 启动脚本 (Windows)

## 方式 1: 使用 Docker (推荐)

```powershell
# 启动 Nacos
docker run -d --name nacos -p 8848:8848 -p 9848:9848 -e MODE=standalone nacos/nacos-server:v2.3.2

# 等待启动完成
Start-Sleep -Seconds 30

# 访问控制台
Start-Process http://localhost:8848/nacos
```

## 方式 2: 直接运行

```powershell
# 1. 下载 Nacos
Invoke-WebRequest -Uri "https://github.com/alibaba/nacos/releases/download/v2.3.2/nacos.zip" -OutFile nacos.zip

# 2. 解压
Expand-Archive -Path nacos.zip -DestinationPath D:\Cache\nacos -Force

# 3. 启动 (Windows)
cd D:\Cache\nacos\bin
.\startup.cmd -m standalone
```

## Nacos 启动后配置

### 1. 登录 Nacos
- 地址: http://localhost:8848/nacos
- 用户名: nacos
- 密码: nacos

### 2. 创建配置

在 Nacos 控制台创建以下配置:

#### shared-config.yml (SHARED_GROUP)
```yaml
spring:
  datasource:
    url: jdbc:postgresql://8.137.116.121:8432/business_db
    username: business
    password: NewPass2024
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 10
      minimum-idle: 2
```

#### gateway-dev.yml (DEFAULT_GROUP)
```yaml
server:
  port: 8080

jwt:
  secret: GatewayJWTSecretKey2024
  expiration: 1800000
```

#### user-service-dev.yml (DEFAULT_GROUP)
```yaml
server:
  port: 8081

jwt:
  secret: UserServiceJWTSecretKey2024
  expiration: 1800000
```

#### config-service-dev.yml (DEFAULT_GROUP)
```yaml
server:
  port: 8082
```

## 启动服务

```powershell
# 启动 Config Service
mvn -f config-service spring-boot:run

# 启动 User Service
mvn -f user-service spring-boot:run

# 启动 Gateway
mvn -f gateway spring-boot:run
```

## 验证

访问 Nacos 控制台查看服务注册:
http://localhost:8848/nacos/#/serviceManagement

应该看到以下服务:
- gateway
- user-service
- config-service
