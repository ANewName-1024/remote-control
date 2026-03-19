# 长期记忆

## 项目经验

### Spring Cloud 微服务
- Gateway 统一鉴权模式
- OIDC 授权服务器实现
- 国密算法集成 (SM2/SM3/SM4)
- **监控模块 Phase 1 已完成** (JVM/DB/System 指标采集 + Prometheus)
- **告警模块 Phase 2 已完成** (AlertRuleEngine + CRUD API)
- **运维模块 Phase 3 已完成** (任务调度 + 脚本执行 + 任务管理)

### 安全实践
- 敏感信息使用环境变量
- Git 提交前检查敏感信息
- 密码强度验证 + 弱密码字典
- JWT + Refresh Token 双 Token 机制
- 敏感配置加密格式: `{cipher}Base64(iv):Base64(encrypted)` (AES-256-GCM)
- 支持 Vault 密钥管理: `{vault}keyname`

### 部署架构
- 本地开发 + frp 内网穿透
- 阿里云服务器资源有限（1.8GB内存）
- 敏感密码定期轮换

## 常用配置

### 环境变量模板
```
DB_HOST, DB_PASSWORD
EUREKA_HOST, EUREKA_PASSWORD
JWT_SECRET
```

### 服务端口
- Gateway: 8080
- user-service: 8081
- config-service: 8082
- Eureka: 9000
- PostgreSQL: 8432
- frps: 9999

## Git 提交规范
- feat: 新功能
- fix: 修复
- docs: 文档
- refactor: 重构
- security: 安全修复

## 排查问题工作流

### 正确流程
1. **先执行命令** - 不要假设，先 run 起来
2. **仔细看错误信息** - Maven/编译器已给出答案
3. **定位具体错误** - 缺少哪个包、哪个类
4. **逐步验证** - 每一步都要确认结果

### 不要这样做
- ❌ 看到输出不完整就假设环境问题
- ❌ 凭猜测下结论
- ❌ 跳过错误信息直接猜原因
- ❌ 思维定势（之前失败=这次也失败）

### 本次教训
- **不要过早下结论** - 实际上 Maven 输出了明确的错误信息
- **错误信息就是答案** - "找不到 jakarta.validation 包" 就是缺依赖
- **简化代码要注意依赖** - 移除 starter 依赖时要小心

### 排查检查清单
```
□ Java 版本正常？
□ Maven 版本正常？
□ 执行 mvn clean compile
□ 查看完整的 ERROR 输出
□ 根据错误信息定位问题
□ 修复后再次验证
```

## 重要教训

### 记忆同步规则
- **每次完成重要功能后，必须立即写入记忆文件**
- 不要依赖"以后会记得"——文件才是真正的记忆
- 写入位置：当日 memory/YYYY-MM-DD.md + 更新 MEMORY.md
