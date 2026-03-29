# 小红书登录指南

## 登录流程

1. 打开 `https://creator.xiaohongshu.com/login`
2. 默认显示**短信登录**表单（手机号 + 验证码）
3. 点击表单**右上角的图片图标**，切换到微信扫码登录
4. 用微信扫描二维码
5. 扫码成功后自动跳转到创作服务平台

## 验证登录状态

访问 `https://creator.xiaohongshu.com/new/home`

## 保存登录状态

```bash
agent-browser cookies save D:\.openclaw\workspace\xiaohongshu\xiaohongshu_cookies.json
```

## 常见问题

### 页面默认显示短信登录，不是微信扫码
**正常现象**。默认就是短信登录。点击表单右上角的图片（不是按钮）切换到扫码。

### 二维码不显示
点击短信登录框右上角的图片图标即可切换到微信扫码模式。

### 扫码后页面没反应
可能已登录但页面没跳转。尝试刷新或手动访问 `https://creator.xiaohongshu.com/new/home`

## 技术说明

- 小红书创作者平台是**单页应用（SPA）**
- 登录后 URL 可能仍是 `/login`，需手动访问 `new/home`
- 平台不支持通过 URL 直接访问笔记管理等子页面
