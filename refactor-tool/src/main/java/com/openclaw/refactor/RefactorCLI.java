package com.openclaw.refactor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.Callable;

/**
 * CLI 入口
 * 
 * 使用示例:
 *   java -jar refactor-tool.jar preview -o com.example -n com.openclaw.ai -d D:\java_project
 *   java -jar refactor-tool.jar execute -o com.example -n com.openclaw.ai -d D:\java_project
 */
@Command(name = "refactor-tool", 
         description = "基于 AST 的 Java 包名重构工具",
         subcommands = {RefactorCLI.PreviewCommand.class, RefactorCLI.ExecuteCommand.class})
public class RefactorCLI implements Callable<Integer> {
    
    private static final Logger log = LoggerFactory.getLogger(RefactorCLI.class);
    
    public static void main(String[] args) {
        int exitCode = new CommandLine(new RefactorCLI()).execute(args);
        System.exit(exitCode);
    }
    
    @Override
    public Integer call() throws Exception {
        CommandLine.usage(this, System.out);
        return 0;
    }
    
    // --- Preview Command ---
    
    @Command(name = "preview", description = "预览修改（不实际修改）")
    public static class PreviewCommand implements Callable<Integer> {
        
        @Option(names = {"-o", "--old"}, required = true, description = "原包名, 如: com.example")
        String oldPackage;
        
        @Option(names = {"-n", "--new"}, required = true, description = "新包名, 如: com.openclaw.ai")
        String newPackage;
        
        @Option(names = {"-d", "--dir"}, required = true, description = "项目根目录")
        String directory;
        
        @Override
        public Integer call() throws Exception {
            log.info("=== 预览模式 ===");
            log.info("原包名: {}", oldPackage);
            log.info("新包名: {}", newPackage);
            log.info("项目目录: {}", directory);
            
            Path rootDir = Path.of(directory);
            if (!Files.exists(rootDir)) {
                log.error("目录不存在: {}", directory);
                return 1;
            }
            
            RefactorEngine engine = new RefactorEngine(oldPackage, newPackage, rootDir);
            engine.analyze();
            
            List<RefactorEngine.ChangeRecord> changes = engine.preview();
            
            System.out.println("\n" + engine.generateReport());
            
            System.out.println("\n提示: 使用 'execute' 命令实际执行修改");
            
            return 0;
        }
    }
    
    // --- Execute Command ---
    
    @Command(name = "execute", description = "执行修改")
    public static class ExecuteCommand implements Callable<Integer> {
        
        @Option(names = {"-o", "--old"}, required = true, description = "原包名")
        String oldPackage;
        
        @Option(names = {"-n", "--new"}, required = true, description = "新包名")
        String newPackage;
        
        @Option(names = {"-d", "--dir"}, required = true, description = "项目根目录")
        String directory;
        
        @Option(names = {"-y", "--yes"}, description = "直接执行，不确认")
        boolean yes;
        
        @Override
        public Integer call() throws Exception {
            log.info("=== 执行模式 ===");
            
            Path rootDir = Path.of(directory);
            if (!Files.exists(rootDir)) {
                log.error("目录不存在: {}", directory);
                return 1;
            }
            
            RefactorEngine engine = new RefactorEngine(oldPackage, newPackage, rootDir);
            engine.analyze();
            
            List<RefactorEngine.ChangeRecord> changes = engine.preview();
            
            if (changes.isEmpty()) {
                System.out.println("没有发现需要修改的地方");
                return 0;
            }
            
            System.out.println(engine.generateReport());
            
            if (!yes) {
                System.out.print("确认执行以上修改? (y/n): ");
                System.out.flush();
                
                // 简单确认（生产环境可用 Scanner）
                System.out.println("\n请手动确认后重新运行，添加 -y 参数直接执行");
                return 1;
            }
            
            engine.execute();
            
            System.out.println("\n✅ 重构完成!");
            
            return 0;
        }
    }
}
