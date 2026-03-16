# Spring Cloud Demo - Deployment Guide

## Prerequisites

### Docker Deployment
- Docker 20.10+
- Docker Compose 2.0+

### VM Deployment
- JDK 21+
- Maven 3.9+
- PostgreSQL client (for SSL certificate)

## Quick Start

### Docker Deployment (Recommended)

1. Build and start all services:
```bash
cd springcloud-demo
docker-compose up --build
```

2. Access services:
- Eureka Dashboard: http://localhost:9000
- Gateway: http://localhost:8080
- User Service: http://localhost:8081
- Config Service: http://localhost:8082

### VM Deployment

1. Build JAR files:
```bash
./deploy.sh build
# or on Windows
mvn clean package -DskipTests
```

2. Copy JAR files to `/opt/springcloud-demo/`:
```bash
mkdir -p /opt/springcloud-demo
cp eureka-server/target/eureka-server-1.0.0.jar /opt/springcloud-demo/
cp config-service/target/config-service-1.0.0.jar /opt/springcloud-demo/
cp user-service/target/user-service-1.0.0.jar /opt/springcloud-demo/
cp gateway/target/gateway-1.0.0.jar /opt/springcloud-demo/
```

3. Create log directory:
```bash
mkdir -p /var/log/springcloud-demo
```

4. Start services:
```bash
./deploy.sh start
```

5. Check status:
```bash
./deploy.sh status
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | localhost | Database host |
| DB_PORT | 5432 | Database port |
| DB_NAME | business_db | Database name |
| DB_USERNAME | business | Database username |
| DB_PASSWORD | Business@123 | Database password |
| EUREKA_CLIENT_SERVICEURL_DEFAULTZONE | http://admin:Eureka@2024!Secure@localhost:9000/eureka/ | Eureka server URL |
| JASYPT_PASSWORD | ConfigSecretKey2024 | Jasypt encryption password |

## Service Ports

| Service | Port |
|---------|------|
| Eureka Server | 9000 |
| Config Service | 8082 |
| User Service | 8081 |
| Gateway | 8080 |

## Docker Commands

```bash
# Build images
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Restart a specific service
docker-compose restart gateway
```
