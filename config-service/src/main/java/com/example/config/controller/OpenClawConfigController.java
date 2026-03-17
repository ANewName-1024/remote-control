package com.example.config.controller;

import com.example.config.entity.OpenClawConfig;
import com.example.config.service.OpenClawConfigService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/openclaw")
public class OpenClawConfigController {

    @Autowired
    private OpenClawConfigService configService;

    @GetMapping("/config/{key}")
    public ResponseEntity<String> getConfig(@PathVariable String key) {
        String value = configService.getValue(key);
        return ResponseEntity.ok(value != null ? value : "");
    }

    @GetMapping("/configs")
    public ResponseEntity<Map<String, String>> getAllConfigs() {
        return ResponseEntity.ok(configService.getAllConfigs());
    }

    @PostMapping("/config")
    public ResponseEntity<OpenClawConfig> saveConfig(
            @RequestParam String key,
            @RequestParam String value,
            @RequestParam(required = false) String configType) {
        OpenClawConfig config = configService.save(key, value, configType != null ? configType : "PARAMETER");
        return ResponseEntity.ok(config);
    }

    @DeleteMapping("/config/{key}")
    public ResponseEntity<Void> deleteConfig(@PathVariable String key) {
        configService.delete(key);
        return ResponseEntity.ok().build();
    }

    @PostMapping("/init")
    public ResponseEntity<String> init() {
        configService.initDefaultConfigs();
        return ResponseEntity.ok("初始化完成");
    }
}
