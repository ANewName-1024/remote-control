#!/bin/bash

# Spring Cloud Demo - VM Deployment Script
# Usage: ./deploy.sh [start|stop|restart|status]

APP_NAME="springcloud-demo"
BASE_DIR="/opt/$APP_NAME"
JAR_FILES=(
    "eureka-server-1.0.0.jar"
    "config-service-1.0.0.jar"
    "user-service-1.0.0.jar"
    "gateway-1.0.0.jar"
)

# Ports
EUREKA_PORT=9000
CONFIG_PORT=8082
USER_PORT=8081
GATEWAY_PORT=8080

# Eureka credentials
EUREKA_USERNAME="admin"
EUREKA_PASSWORD="Eureka@2024!Secure"

# Database credentials
DB_HOST="8.137.116.121"
DB_PORT="8432"
DB_NAME="business_db"
DB_USERNAME="business"
DB_PASSWORD="Business@123"

# Build function
build() {
    echo "Building all services..."
    mvn clean package -DskipTests
    echo "Build complete!"
}

# Start function
start() {
    echo "Starting all services..."
    
    # Start Eureka Server
    echo "Starting Eureka Server on port $EUREKA_PORT..."
    nohup java -jar \
        -Deureka.instance.hostname=localhost \
        -Deureka.client.service-url.defaultZone=http://$EUREKA_USERNAME:$EUREKA_PASSWORD@localhost:$EUREKA_PORT/eureka/ \
        -jar $BASE_DIR/eureka-server-1.0.0.jar \
        > /var/log/$APP_NAME/eureka.log 2>&1 &
    
    sleep 5
    
    # Start Config Service
    echo "Starting Config Service on port $CONFIG_PORT..."
    nohup java -jar \
        -Dspring.datasource.url=jdbc:postgresql://$DB_HOST:$DB_PORT/$DB_NAME?ssl=true\&sslmode=verify-full \
        -Dspring.datasource.username=$DB_USERNAME \
        -Dspring.datasource.password=$DB_PASSWORD \
        -Deureka.client.service-url.defaultZone=http://$EUREKA_USERNAME:$EUREKA_PASSWORD@localhost:$EUREKA_PORT/eureka/ \
        -Djasypt.encryptor.password=ConfigSecretKey2024 \
        -jar $BASE_DIR/config-service-1.0.0.jar \
        > /var/log/$APP_NAME/config.log 2>&1 &
    
    sleep 5
    
    # Start User Service
    echo "Starting User Service on port $USER_PORT..."
    nohup java -jar \
        -Dspring.datasource.url=jdbc:postgresql://$DB_HOST:$DB_PORT/$DB_NAME?ssl=true\&sslmode=verify-full \
        -Dspring.datasource.username=$DB_USERNAME \
        -Dspring.datasource.password=$DB_PASSWORD \
        -Deureka.client.service-url.defaultZone=http://$EUREKA_USERNAME:$EUREKA_PASSWORD@localhost:$EUREKA_PORT/eureka/ \
        -jar $BASE_DIR/user-service-1.0.0.jar \
        > /var/log/$APP_NAME/user.log 2>&1 &
    
    sleep 5
    
    # Start Gateway
    echo "Starting Gateway on port $GATEWAY_PORT..."
    nohup java -jar \
        -Deureka.client.service-url.defaultZone=http://$EUREKA_USERNAME:$EUREKA_PASSWORD@localhost:$EUREKA_PORT/eureka/ \
        -jar $BASE_DIR/gateway-1.0.0.jar \
        > /var/log/$APP_NAME/gateway.log 2>&1 &
    
    echo "All services started!"
    status
}

# Stop function
stop() {
    echo "Stopping all services..."
    for jar in "${JAR_FILES[@]}"; do
        pid=$(ps aux | grep "$jar" | grep -v grep | awk '{print $2}')
        if [ -n "$pid" ]; then
            echo "Stopping $jar (PID: $pid)"
            kill $pid
        fi
    done
    echo "All services stopped!"
}

# Status function
status() {
    echo "Service Status:"
    for jar in "${JAR_FILES[@]}"; do
        if ps aux | grep "$jar" | grep -v grep > /dev/null; then
            echo "  ✓ $jar - RUNNING"
        else
            echo "  ✗ $jar - STOPPED"
        fi
    done
}

# Main
case "$1" in
    build)
        build
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 3
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {build|start|stop|restart|status}"
        exit 1
        ;;
esac
