# Java Package Refactoring Skill

## 概述

将 Java 项目从旧包路径重构到新包路径（如 `com.example.ops` → `com.openclaw.ai`），同时保持功能正常运行。

## 触发条件

当用户请求以下内容时激活：
- "重构 Java 包"
- "迁移包路径"
- "重命名 package"
- "Java 项目架构调整"
- "将 xxx 移动到 yyy 包"

---

## 执行流程

### Phase 1: 分析现有代码结构

```powershell
# 1. 查看当前包结构
Get-ChildItem "项目路径\ops-service\src\main\java\com\example\ops"
```

### Phase 2: 创建新包结构（不移动文件）

**关键原则**：直接修改文件内容，不移动位置，避免编码问题。

```powershell
# 1. 创建目标包目录
New-Item -ItemType Directory -Force -Path "项目路径\ops-service\src\main\java\com\openclaw\ai\新模块\service"

# 2. 复制并修改文件（使用 write tool）
```

### Phase 3: 迁移服务（按依赖顺序）

**依赖顺序**（无依赖 → 有依赖）：

| 顺序 | 服务 | 目标包 |
|------|------|--------|
| 1 | NotificationService | notify |
| 2 | ScriptExecutionService | workflow |
| 3 | TaskSchedulerService | workflow |
| 4 | WorkflowService | workflow |
| 5 | RbacService | rbac |
| 6 | AutoHealService | ops |
| 7 | GrayReleaseService | ops |
| 8 | OpsTaskService | ops |
| 9 | MetricsService | monitor |
| 10 | KnowledgeBaseService | knowledge |
| 11 | AIService | knowledge |
| 12 | AIChatService | chat |

### Phase 4: 迁移控制器

```powershell
# 按模块迁移控制器
# 更新 import 引用新包路径
```

### Phase 5: 删除旧文件

```powershell
# 确认新代码编译通过后再删除旧文件
Remove-Item "旧文件路径"
```

### Phase 6: 编译验证

```powershell
cd "项目路径"
mvn compile -pl ops-service
```

---

## 工作流抽象模板

### 服务模板

```java
package com.openclaw.ai.新模块.service;

import org.springframework.stereotype.Service;

@Service
public class NewServiceName {

    // 业务逻辑
    
    // 内部类
    public static class Entity {
        private final String id;
        // getters
    }
}
```

### 控制器模板

```java
package com.openclaw.ai.新模块.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/ops/新模块")
public class NewController {

    @Autowired
    private NewServiceName newServiceName;

    @GetMapping
    public List<?> list() {
        return newServiceName.getAll();
    }
}
```

---

## 注意事项

### 编码问题

❌ **不要使用**：
- PowerShell Move-Item / Copy-Item（会导致编码损坏）
- IDE 外的文件移动操作

✅ **使用**：
- `write` tool 直接创建/修改文件
- 确保使用 `-Encoding UTF8`

### 编译验证

- 每迁移一个模块立即编译
- 失败立即回退：`git checkout -- .`
- 保持编译通过是最高优先级

### 依赖管理

- 先迁移被依赖的服务
- 后迁移依赖其他服务的模块
- 更新 import 语句

---

## 示例：迁移 NotificationService

### 1. 创建新文件

```java
package com.openclaw.ai.notify.service;

// 复制原代码，修改 package 声明
@Service
public class NotificationService {
    // ... 原代码
}
```

### 2. 编译验证

```powershell
mvn compile -pl ops-service
```

### 3. 删除旧文件

```powershell
Remove-Item "旧路径\NotificationService.java"
```

---

## 回退方案

如果遇到编码问题或编译失败：

```powershell
# 回退所有更改
cd "项目路径"
git checkout -- .
```

---

## 适用场景

- Spring Boot 微服务包路径重构
- 多模块项目架构调整
- 企业级 Java 项目命名规范调整
