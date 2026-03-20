# refactor-skill

基于 AST 的 Java 包名重构工具，模拟 IDEA Refactor 底层原理。

## 功能

- **AST 解析**：使用 JavaParser 解析源代码，理解代码结构
- **符号追踪**：跟踪包/类/方法的定义和引用
- **智能替换**：识别 package 声明、import 语句、类型引用
- **目录重命名**：自动重命名包目录结构
- **预览模式**：先预览所有修改，确认后再执行

## 使用方法

```bash
# 预览模式（查看所有修改，不实际修改）
java -jar refactor-tool.jar preview -o com.example -n com.openclaw.ai -d /path/to/project

# 执行模式
java -jar refactor-tool.jar execute -o com.example -n com.openclaw.ai -d /path/to/project -y
```

## 参数

- `-o, --old`: 原包名（如 com.example）
- `-n, --new`: 新包名（如 com.openclaw.ai）
- `-d, --dir`: 项目根目录
- `-y, --yes`: 直接执行，不确认（可选）

## 工作原理

1. **解析 AST**：将 Java 源代码解析为抽象语法树
2. **构建符号索引**：跟踪所有类型声明和引用
3. **识别修改点**：找出 package 声明、import 语句、类型引用
4. **批量修改**：按文件分组，逐个修改
5. **重命名目录**：最后重命名包目录

## 构建

```bash
cd refactor-tool
mvn clean package -DskipTests
```

## 输出 JAR

`target/refactor-tool-1.0.0.jar`
