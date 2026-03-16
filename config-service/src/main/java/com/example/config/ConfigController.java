package com.example.config;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/config")
public class ConfigController {
    
    @Autowired
    private ConfigService configService;
    
    /**
     * 获取所有配置
     */
    @GetMapping("/list")
    public List<SysConfig> list() {
        return configService.getAllConfigs();
    }
    
    /**
     * 获取配置详情（含脱敏）
     */
    @GetMapping("/{id}")
    public SysConfig get(@PathVariable Long id) {
        return configService.getConfigMasked(id);
    }
    
    /**
     * 获取配置详情（解密）
     */
    @GetMapping("/{id}/decrypt")
    public SysConfig getDecrypt(@PathVariable Long id) {
        return configService.getConfig(id);
    }
    
    /**
     * 创建配置
     */
    @PostMapping
    public SysConfig create(@Valid @RequestBody SysConfig config, 
                           @RequestHeader(value = "X-Operator", defaultValue = "system") String operator) {
        return configService.createConfig(config, operator);
    }
    
    /**
     * 更新配置
     */
    @PutMapping("/{id}")
    public SysConfig update(@PathVariable Long id, 
                          @Valid @RequestBody SysConfig config,
                          @RequestHeader(value = "X-Operator", defaultValue = "system") String operator) {
        return configService.updateConfig(id, config, operator);
    }
    
    /**
     * 回滚配置
     */
    @PostMapping("/{id}/rollback/{historyId}")
    public SysConfig rollback(@PathVariable Long id, 
                            @PathVariable Long historyId,
                            @RequestHeader(value = "X-Operator", defaultValue = "system") String operator) {
        return configService.rollbackConfig(id, historyId, operator);
    }
    
    /**
     * 获取配置历史
     */
    @GetMapping("/{id}/history")
    public List<ConfigHistory> history(@PathVariable Long id) {
        return configService.getConfigHistory(id);
    }
    
    /**
     * 删除配置
     */
    @DeleteMapping("/{id}")
    public Map<String, Object> delete(@PathVariable Long id,
                                     @RequestHeader(value = "X-Operator", defaultValue = "system") String operator) {
        configService.deleteConfig(id, operator);
        return Map.of("message", "删除成功");
    }
    
    /**
     * 加密测试接口
     */
    @PostMapping("/encrypt")
    public Map<String, String> encrypt(@RequestBody Map<String, String> request) {
        String data = request.get("data");
        String encrypted = new EncryptionService().encrypt(data);
        return Map.of("encrypted", encrypted);
    }
}
