# 小红书运营 Skill

小红书创作者平台自动化运营。

## 登录

1. 打开 `https://creator.xiaohongshu.com/login`
2. 默认显示**短信登录**表单
3. 点击表单**右上角的图片**（不是任何按钮）切换到微信扫码
4. 扫码成功后页面跳转到 `new/home`
5. 保存 cookies：
   ```bash
   agent-browser cookies save D:\.openclaw\workspace\xiaohongshu\xiaohongshu_cookies.json
   ```

### 登录后验证
- 访问 `https://creator.xiaohongshu.com/new/home` 确认登录态

## 发布图文笔记

### Step 1: 进入发布页
1. `agent-browser open https://creator.xiaohongshu.com/publish/publish`
2. 等待 3 秒后快照
3. 点击**左侧"上传图文"**（第二个，可能标号 e5 或 e6）

### Step 2: 上传图片
**重要**：不能用 `ref` 编号，必须用 CSS 选择器：
```bash
agent-browser upload "input.upload-input" <文件路径>
```
例如：`agent-browser upload "input.upload-input" D:/temp/image.png`

### Step 3: 填写内容
- 标题输入框：快照中为 `textbox "填写标题会有更多赞哦"`
- 正文输入框：快照中为无名称的 `textbox`（较大的那个）
- 标签：系统会推荐热门标签，可直接点击添加

### Step 4: 发布
- 滚动到页面底部找到**"发布"**按钮
- 点击后等待 5-8 秒
- URL 出现 `published=true` 表示发布成功

## 常见问题

### 文字配图生成按钮点了没反应
小红书 AI 生成有后端限制，**不要等生成**，直接上传真实图片更可靠。

### 文件上传用 ref 编号失败
小红书上传组件是动态的，必须用 CSS 选择器：
```bash
# 错误
agent-browser upload "ref=e8" <文件>

# 正确
agent-browser upload "input.upload-input" <文件>
```

### 找不到发布按钮
发布按钮在页面**最底部**，需要滚动才能看到。

### 创作者平台是 SPA
小红书创作者平台是**单页应用（SPA）**：
- 切换页面后 URL **可能不变**
- 快照只能看到可交互元素，看不到完整导航结构
- **不要尝试通过 URL 访问笔记管理页面**（返回"页面不见了"）
- 笔记管理只能通过左侧导航逐级点击进入

### 删除笔记
创作者平台没有独立的笔记管理 URL。

**方案**：通过主页笔记缩略图进入详情：
1. 在 `new/home` 页面找到笔记缩略图（`image "note"`）
2. 点击进入笔记详情页
3. 找到删除选项

**最可靠方案**：手机小红书 App 删除（最快）

## 飞书发图片

发送图片到飞书时，图片必须放在**允许的目录**：
```bash
# 正确路径
C:\Users\Administrator\.openclaw\media\<文件名>

# 错误路径（not allowed）
D:\.openclaw\workspace\<文件名>
```

操作：
```bash
copy <图片路径> C:\Users\Administrator\.openclaw\media\<文件名>
openclaw message send --channel feishu --target <user_id> --media C:\Users\Administrator\.openclaw\media\<文件名> --message "内容"
```

## 文件路径
- cookies: `D:\.openclaw\workspace\xiaohongshu\xiaohongshu_cookies.json`
- 草稿目录: `D:\.openclaw\workspace\xiaohongshu\drafts\`
- 发布成功标识: URL 包含 `published=true`
