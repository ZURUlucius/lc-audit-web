# LC Audit Web - 信用证审核 Web 应用

基于 lc-audit Skill 构建的团队共享信用证审核工具。

## 功能

- 上传信用证 PDF + 交单文件 → 自动生成专业审核报告
- 支持 OCR 识别扫描件
- 条款异常分析、交叉核对、不符点检测
- 输出专业 PDF 报告

## 快速开始（本地）

```bash
pip install -r requirements.txt
python app.py
```

然后打开 http://localhost:5000

## 部署到云端

详见 [DEPLOY.md](DEPLOY.md)

## 项目结构

```
├── app.py              # Flask 主应用
├── requirements.txt    # Python 依赖
├── static/
│   ├── style.css       # 页面样式
│   └── script.js       # 前端交互逻辑
├── templates/
│   └── index.html      # 主页面
├── utils/
│   ├── pdf_extractor.py    # PDF文本提取(含OCR)
│   ├── lc_analyzer.py      # LC条款分析引擎
│   ├── compliance.py       # 交单合规检查引擎
│   └── report_builder.py   # PDF报告生成器
└── README.md
```
