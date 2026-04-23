# LC Audit Web 部署指南

本教程指导你如何将 LC Audit Web 应用部署到云端，让团队成员都能通过浏览器使用。

## 方案一：Render 部署（推荐，最简单）

### 第 1 步：注册 Render 账号

1. 打开 https://render.com
2. 点击 **Sign Up**（注册）
3. 选择 **Sign up with GitHub**（推荐，因为代码需要放在 GitHub 上）
   - 或者用邮箱注册也可以

> 完全免费，不需要绑信用卡。

### 第 2 步：上传代码到 GitHub

1. 打开 https://github.com/new
2. Repository name 填：`lc-audit-web`
3. 选择 **Private**（私有仓库，只有你能看到）
4. 点击 **Create repository**
5. 创建完成后，你会看到一个页面提示你上传代码

#### 如果你熟悉 Git 命令行：

```bash
# 在 lc-audit-web 目录下执行：
git init
git add .
git commit -m "Initial commit: LC Audit Web"
git remote add origin https://github.com/你的用户名/lc-audit-web.git
git push -u origin main
```

#### 如果不熟悉 Git：

1. 在 GitHub 新建仓库的页面，找到 **"uploading an existing file"** 链接并点击
2. 把 `lc-audit-web` 文件夹里的所有文件拖进去（除了 `__pycache__` 文件夹）
3. 滚动到底部点击 **Commit changes**

### 第 3 步：在 Render 上创建服务

1. 登录 Render 后台
2. 点击 **New +**
3. 选择 **Web Service**
4. 连接你的 GitHub 账号 → 选择 `lc-audit-web` 仓库 → 点击 **Connect**
5. 填写以下配置：

| 配置项 | 值 |
|--------|-----|
| **Name** | `lc-audit-web`（随便起） |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python app.py` |
| **Instance Type** | Free（免费） |

6. 点击 **Advanced** 展开高级选项：
   - 找到 **Health Check Path**，填 `/health`
7. 点击 **Create Web Service**

### 第 4 步：等待部署完成（约 3-5 分钟）

- Render 会自动安装依赖、启动应用
- 你会看到进度条和日志输出
- 完成后会出现一个网址，类似：`https://lc-audit-web.onrender.com`
- **把这个网址分享给团队即可使用！**

---

## 方案二：Railway 部署（同样免费）

### 第 1 步：注册 Railway

1. 打开 https://railway.app
2. 用 GitHub 或邮箱注册

### 第 2 步：部署项目

1. 登录后，点击 **New Project**
2. 选择 **Deploy from GitHub repo**
3. 授权 GitHub 并选择 `lc-audit-web` 仓库
4. Railway 会自动检测到 Python 项目
5. 它会提示配置 Start Command，填写：
   ```
   python app.py
   ```
6. 点击 **Deploy**

### 第 3 步：获取访问链接

- 部署完成后 Railway 会生成一个 URL
- 类似：`https://xxx.up.railway.app`
- 分享给团队使用

---

## 方案三：本地运行（自己电脑上用）

### 快速启动：

```bash
# 1. 进入项目目录
cd lc-audit-web

# 2. 安装依赖（首次运行）
pip install -r requirements.txt

# 3. 启动应用
python app.py
```

然后打开浏览器访问 **http://localhost:5000**

> 本地版本只有你自己能用。要团队共享请使用方案一或方案二。

---

## 常见问题

### Q: 免费额度够用吗？
A: 够的。LC 审核是"用时启动"的模式，不是常驻高负载服务。Render 的免费层每月有 750 小时，足够小团队每天几十次审核。

### Q: 上传文件大小有限制吗？
A: 当前设置为单个文件最大 100MB。如果需要更大，可以修改 app.py 中的 `MAX_CONTENT_LENGTH`。

### Q: 报告会保存多久？
A: 生成的报告 PDF 存储在服务器临时目录，服务器重启后会清除。建议下载到本地保存。

### Q: OCR 识别准确率怎么样？
A: 对清晰扫描件约 90-95%。模糊/手写体可能更低。重要字段建议人工核对。

### Q: 安全吗？
A: 上传的文件仅用于临时处理，不会永久存储。PDF 提取完文本后立即删除原文件。但建议不要在公开网络上处理高度机密的信用证。

---

## 项目结构说明

```
lc-audit-web/
├── app.py                  # Flask 主应用入口
├── requirements.txt        # Python 依赖列表
├── runtime.txt             # Render 运行环境指定 (Python 3.11)
├── .gitignore              # Git 忽略规则
├── README.md               # 项目说明
├── DEPLOY.md               # 你正在看的这份部署指南
├── static/
│   ├── style.css           # 页面样式
│   └── script.js           # 前端交互逻辑
├── templates/
│   └── index.html          # 主页面模板
└── utils/
    ├── pdf_extractor.py    # PDF文本提取(含OCR)
    ├── lc_analyzer.py      # LC条款分析引擎
    ├── compliance.py       # 交单合规检查引擎
    └── report_builder.py   # PDF报告生成器
```
