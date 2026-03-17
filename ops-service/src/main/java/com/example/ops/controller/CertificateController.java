package com.example.ops.controller;

import com.example.ops.service.cert.CertificateRotationService;
import com.example.ops.service.cert.CertificateRotationService.CertificateInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * 证书管理控制器
 */
@RestController
@RequestMapping("/ops/cert")
public class CertificateController {

    @Autowired
    private CertificateRotationService certService;

    /**
     * 获取证书信息
     */
    @GetMapping("/info")
    public ResponseEntity<Map<String, Object>> getCertificateInfo() {
        CertificateInfo info = certService.getCertificateInfo();
        
        Map<String, Object> result = new HashMap<>();
        if (info != null) {
            result.put("subject", info.getSubject());
            result.put("issuer", info.getIssuer());
            result.put("validFrom", info.getValidFrom());
            result.put("validTo", info.getValidTo());
            result.put("serialNumber", info.getSerialNumber());
            result.put("isExpired", info.isExpired());
            result.put("isExpiringSoon", info.isExpiringSoon(30));
        }
        
        return ResponseEntity.ok(result);
    }

    /**
     * 手动触发证书轮转
     */
    @PostMapping("/rotate")
    public ResponseEntity<Map<String, String>> rotateCertificate() {
        try {
            certService.rotateCertificate();
            
            Map<String, String> result = new HashMap<>();
            result.put("status", "success");
            result.put("message", "证书轮转完成");
            
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            Map<String, String> result = new HashMap<>();
            result.put("status", "error");
            result.put("message", "证书轮转失败: " + e.getMessage());
            
            return ResponseEntity.status(500).body(result);
        }
    }

    /**
     * 检查证书是否即将过期
     */
    @GetMapping("/check")
    public ResponseEntity<Map<String, Boolean>> checkCertificate() {
        boolean expiringSoon = certService.isCertificateExpiringSoon();
        
        Map<String, Boolean> result = new HashMap<>();
        result.put("expiringSoon", expiringSoon);
        
        return ResponseEntity.ok(result);
    }
}
