package com.openclaw.refactor;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.PackageDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedReferenceTypeDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 基于 AST 的 Java 包名重构引擎
 * 
 * 核心原理：
 * 1. 解析 AST 理解代码结构
 * 2. 构建符号索引，跟踪包/类/方法的定义和引用
 * 3. 识别所有需要修改的位置
 * 4. 批量修改并保持代码语义
 */
public class RefactorEngine {
    
    private static final Logger log = LoggerFactory.getLogger(RefactorEngine.class);
    
    private final String oldPackage;
    private final String newPackage;
    private final Path rootDir;
    
    private final List<ChangeRecord> changes = new ArrayList<>();
    private final Map<String, Set<String>> packageToFiles = new HashMap<>();
    
    public RefactorEngine(String oldPackage, String newPackage, Path rootDir) {
        this.oldPackage = oldPackage;
        this.newPackage = newPackage;
        this.rootDir = rootDir;
    }
    
    /**
     * 扫描并分析所有需要修改的文件
     */
    public void analyze() throws IOException {
        log.info("开始分析项目: {} -> {}", oldPackage, newPackage);
        
        Files.walk(rootDir)
            .filter(p -> p.toString().endsWith(".java"))
            .filter(p -> !p.toString().contains("/target/"))
            .filter(p -> !p.toString().contains("/test/"))
            .forEach(this::analyzeFile);
        
        log.info("分析完成，共发现 {} 处需要修改", changes.size());
    }
    
    private void analyzeFile(Path javaFile) {
        try {
            // 配置 AST 解析器
            CombinedTypeSolver typeSolver = new CombinedTypeSolver();
            typeSolver.add(new ReflectionTypeSolver());
            
            ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(new JavaSymbolSolver(typeSolver));
            
            JavaParser parser = new JavaParser(config);
            ParseResult<CompilationUnit> result = parser.parse(javaFile);
            
            if (!result.isSuccessful()) {
                log.warn("解析失败: {}", javaFile);
                return;
            }
            
            CompilationUnit cu = result.getResult().get();
            
            // 检查 package 声明
            Optional<PackageDeclaration> packageDecl = cu.getPackageDeclaration();
            if (packageDecl.isPresent()) {
                String pkg = packageDecl.get().getNameAsString();
                if (pkg.equals(oldPackage) || pkg.startsWith(oldPackage + ".")) {
                    // 需要修改 package 声明
                    String newPkg = pkg.replace(oldPackage, newPackage);
                    changes.add(new ChangeRecord(
                        ChangeType.PACKAGE_DECLARATION,
                        javaFile.toString(),
                        pkg,
                        newPkg,
                        "修改 package 声明"
                    ));
                    
                    // 记录包和文件映射
                    packageToFiles.computeIfAbsent(pkg, k -> new HashSet<>())
                        .add(javaFile.toString());
                }
            }
            
            // 检查 import 语句
            for (ImportDeclaration importDecl : cu.getImports()) {
                String importName = importDecl.getNameAsString();
                if (importName.equals(oldPackage) || importName.startsWith(oldPackage + ".")) {
                    String newImport = importName.replace(oldPackage, newPackage);
                    changes.add(new ChangeRecord(
                        ChangeType.IMPORT_DECLARATION,
                        javaFile.toString(),
                        importName,
                        newImport,
                        "修改 import 语句"
                    ));
                }
            }
            
            // 检查类型引用（通过符号解析）
            for (TypeDeclaration<?> type : cu.getTypes()) {
                try {
                    ResolvedReferenceTypeDeclaration resolved = type.resolve();
                    String typePackage = resolved.getPackageName();
                    
                    if (typePackage.equals(oldPackage) || typePackage.startsWith(oldPackage + ".")) {
                        // 类引用需要修改
                        String fullName = resolved.getQualifiedName();
                        String newName = fullName.replace(oldPackage, newPackage);
                        changes.add(new ChangeRecord(
                            ChangeType.TYPE_REFERENCE,
                            javaFile.toString(),
                            fullName,
                            newName,
                            "修改类型引用: " + type.getNameAsString()
                        ));
                    }
                } catch (Exception e) {
                    // 符号解析失败，跳过
                }
            }
            
        } catch (Exception e) {
            log.error("分析文件失败: {}", javaFile, e);
        }
    }
    
    /**
     * 执行修改（预览模式）
     */
    public List<ChangeRecord> preview() {
        return changes.stream()
            .collect(Collectors.toList());
    }
    
    /**
     * 执行修改（实际写入文件）
     */
    public void execute() throws IOException {
        log.info("开始执行修改，共 {} 处", changes.size());
        
        // 按文件分组修改
        Map<String, List<ChangeRecord>> changesByFile = changes.stream()
            .collect(Collectors.groupingBy(ChangeRecord::getFilePath));
        
        for (Map.Entry<String, List<ChangeRecord>> entry : changesByFile.entrySet()) {
            String filePath = entry.getKey();
            List<ChangeRecord> fileChanges = entry.getValue();
            
            applyChangesToFile(filePath, fileChanges);
        }
        
        // 重命名目录
        renameDirectories();
        
        log.info("修改完成!");
    }
    
    private void applyChangesToFile(String filePath, List<ChangeRecord> changes) throws IOException {
        Path path = Paths.get(filePath);
        String content = Files.readString(path, StandardCharsets.UTF_8);
        String modified = content;
        
        for (ChangeRecord change : changes) {
            // 直接替换（不用单词边界，避免匹配问题）
            if (modified.contains(change.getOldValue())) {
                modified = modified.replace(change.getOldValue(), change.getNewValue());
            }
        }
        
        Files.writeString(path, modified, StandardCharsets.UTF_8);
        log.info("已修改文件: {}", filePath);
    }
    
    /**
     * 重命名包目录
     */
    private void renameDirectories() throws IOException {
        String oldPathStr = oldPackage.replace(".", "/");
        String newPathStr = newPackage.replace(".", "/");
        
        // 找到所有需要重命名的目录
        List<Path> dirsToRename = new ArrayList<>();
        
        Files.walk(rootDir)
            .filter(p -> p.toString().endsWith(oldPathStr))
            .forEach(dirsToRename::add);
        
        for (Path dir : dirsToRename) {
            Path parent = dir.getParent();
            Path newDir = parent.resolve(newPathStr);
            
            // 如果目标目录不存在才重命名
            if (!Files.exists(newDir)) {
                Files.move(dir, newDir);
                log.info("已重命名目录: {} -> {}", dir, newDir);
            }
        }
    }
    
    /**
     * 生成修改报告
     */
    public String generateReport() {
        StringBuilder sb = new StringBuilder();
        sb.append("=== 重构报告 ===\n");
        sb.append("原包名: ").append(oldPackage).append("\n");
        sb.append("新包名: ").append(newPackage).append("\n");
        sb.append("总修改数: ").append(changes.size()).append("\n\n");
        
        // 按类型分组
        Map<ChangeType, List<ChangeRecord>> byType = changes.stream()
            .collect(Collectors.groupingBy(ChangeRecord::getType));
        
        for (ChangeType type : ChangeType.values()) {
            List<ChangeRecord> typeChanges = byType.get(type);
            if (typeChanges != null && !typeChanges.isEmpty()) {
                sb.append("【").append(type).append("】(").append(typeChanges.size()).append("处)\n");
                
                // 按文件分组
                Map<String, List<ChangeRecord>> byFile = typeChanges.stream()
                    .collect(Collectors.groupingBy(ChangeRecord::getFilePath));
                
                for (Map.Entry<String, List<ChangeRecord>> entry : byFile.entrySet()) {
                    sb.append("  文件: ").append(entry.getKey()).append("\n");
                    for (ChangeRecord c : entry.getValue()) {
                        sb.append("    - ").append(c.getOldValue())
                          .append(" -> ").append(c.getNewValue()).append("\n");
                    }
                }
                sb.append("\n");
            }
        }
        
        return sb.toString();
    }
    
    // --- 内部类 ---
    
    public enum ChangeType {
        PACKAGE_DECLARATION,  // package 声明
        IMPORT_DECLARATION,   // import 语句
        TYPE_REFERENCE,       // 类型引用
        ANNOTATION            // 注解引用
    }
    
    public static class ChangeRecord {
        private final ChangeType type;
        private final String filePath;
        private final String oldValue;
        private final String newValue;
        private final String description;
        
        public ChangeRecord(ChangeType type, String filePath, String oldValue, 
                           String newValue, String description) {
            this.type = type;
            this.filePath = filePath;
            this.oldValue = oldValue;
            this.newValue = newValue;
            this.description = description;
        }
        
        public ChangeType getType() { return type; }
        public String getFilePath() { return filePath; }
        public String getOldValue() { return oldValue; }
        public String getNewValue() { return newValue; }
        public String getDescription() { return description; }
        
        @Override
        public String toString() {
            return String.format("[%s] %s: %s -> %s", type, filePath, oldValue, newValue);
        }
    }
}
