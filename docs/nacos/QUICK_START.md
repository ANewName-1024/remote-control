# 快速启动 Nacos (开发环境)

## 方式 1: 使用嵌入式 Nacos (Java 启动)

在 config-service 中添加嵌入式 Nacos 依赖：

```xml
<!-- 嵌入式 Nacos (开发环境用) -->
<dependency>
    <groupId>com.alibaba.nacos</groupId>
    <artifactId>nacos-embedded</artifactId>
    <version>2023.0.1.2</version>
</dependency>
```

## 方式 2: 使用 Spring Boot 快速启动

创建启动脚本 (start-nacos.bat):

```batch
@echo off
set NACOS_VERSION=2.3.2
set NACOS_HOME=D:\Cache\nacos

if not exist "%NACOS_HOME%" (
    echo 请先下载 Nacos Server
    echo 下载地址: https://github.com/alibaba/nacos/releases
    exit /b 1
)

cd /d "%NACOS_HOME%\bin"
start cmd /c "standalone.bat"
```

## 方式 3: 使用 Docker Compose (推荐)

创建 docker-compose.yml:

```yaml
version: '3.8'
services:
  nacos:
    image: nacos/nacos-server:v2.3.2
    container_name: nacos
    ports:
      - "8848:8848"
      - "9848:9848"
    environment:
      - MODE=standalone
      - SPRING_DATASOURCE_PLATFORM=postgresql
      - DB_URL=jdbc:postgresql://8.137.116.121:8432/nacos_config
      - DB_USER=business
      - DB_PASSWORD=NewPass2024
    volumes:
      - ./nacos/logs:/home/nacos/logs
```

启动:
```bash
docker-compose up -d
```

## 方式 4: 直接下载运行

```powershell
# 创建目录
New-Item -ItemType Directory -Force -Path D:\Cache\nacos

# 下载 (使用国内镜像)
Invoke-WebRequest -Uri "https://nacos.io/download/nacos-server/nacos/nacos-server-2.3.2.zip" -OutFile D:\Cache\nacos.zip

# 解压
Expand-Archive -Path D:\Cache\nacos.zip -DestinationPath D:\Cache\nacos -Force

# 启动 (Windows)
cd D:\Cache\nacos\bin
.\startup.cmd -m standalone
```

## 验证 Nacos 启动

访问控制台: http://localhost:8848/nacos

- 用户名: nacos
- 密码: nacos

## 下一步

Nacos 启动后，在 Nacos 控制台创建配置，然后修改各服务的 bootstrap.yml 启用 Nacos 配置。
