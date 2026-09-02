# 最终发布版部署与启动指南

## 1. 项目定位

该项目最终已落地为“本地控制端 + 云端执行端”的论文复现产品，适合：

- 本地任务提交和状态查看
- 云端代码执行与环境适配
- 自动抓取论文仓库候选
- 日志回流与分析输出
- GitHub 展示与项目说明

它已经不再只是一个脚手架，而是一套更接近真实产品的研究工作流系统。

## 2. 交付文件导航

- `README.md`：项目总览和仓库介绍
- `paper_repro_app/README.md`：产品说明和应用入口
- `docs/product-showcase.html`：展示型产品页
- `docs/requirements-analysis.md`：需求分析与用户痛点
- `docs/final-delivery-package.md`：最终交付说明
- `scripts/start_release.py`：一键启动脚本

## 3. 一键启动（推荐）

在仓库根目录执行：

```bash
python scripts/start_release.py
```

脚本会自动：

- 创建项目根目录 `.venv`
- 安装 `requirements.txt`
- 安装 `paper_repro_app/requirements.txt`
- 检测当前环境和端口状态
- 自动打开浏览器访问：

```text
http://127.0.0.1:8505
```

如果同一局域网下的手机需要访问，也会输出：

```text
http://<本机IP>:8505
```

## 4. Windows 一键启动

如果你是 Windows 用户，直接双击执行：

```text
scripts/start_release.bat
```

如果 `bat` 文件不支持直接双击，请使用：

```bat
python scripts/start_release.py
```

## 5. 手动启动

如果不想使用脚本，也可以手动启动：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install -r paper_repro_app/requirements.txt
streamlit run paper_repro_app/app.py --server.address 0.0.0.0 --server.port 8505
```

Windows 命令：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r paper_repro_app/requirements.txt
streamlit run paper_repro_app/app.py --server.address 0.0.0.0 --server.port 8505
```

## 6. 访问方式

### 6.1 本机访问

```text
http://127.0.0.1:8505
```

### 6.2 局域网 / 手机访问

在同一 Wi‑Fi 或局域网下访问：

```text
http://<你的电脑IP>:8505
```

## 7. 产品说明

### 7.1 本地控制端

- 论文 URL 输入
- 代码仓库候选补充
- 任务流程管理
- 日志查看
- 结果和报告输出

### 7.2 云端执行端

- SSH 连接
- 拉取代码
- 创建和切换环境
- 安装依赖
- 执行验证脚本

### 7.3 智能分析模块

- 文章关键信息抽取
- 仓库目标识别
- 创新点和风险判断
- 复现结论汇总

### 7.4 交付输出

- Markdown 报告
- JSON 结构化记录
- 实验对比表
- 项目总结说明

## 8. 发布前建议

在公开发布或提交 GitHub 前，建议：

- 确认不提交 `.venv`、密钥、云端配置
- 保留 README、文档、应用代码和脚本
- 把 `docs/product-showcase.html` 作为展示页附件
- 提交项目总结和需求分析文档

## 9. GitHub 提交示例

```bash
git init
git add .
git commit -m "feat: final product release of paper reproduction runner"
git branch -M main
git remote add origin https://github.com/yourname/your-repo.git
git push -u origin main
```

## 10. 注意事项

- 不要将 SSH 私钥上传到 GitHub。
- 云端资源仍需用户自有账号或服务器权限。
- 真正的论文复现仍受目标仓库复杂度影响，系统是“工程工具”，不是万能自动复现器。
- 适合用于展示、落地和工程演示，而不仅是概念验证。

## 11. 结论

这个版本已经从“原型脚手架”成长为“可展示、可交付、可迭代”的论文复现产品。其价值在于：

- 降低复现门槛
- 提升科研工程化体验
- 让项目更有展示感
- 让作品更适合 GitHub 和面试表达

如果你希望进一步提升成“商业/产品化”形态，还可以继续扩展：

- 更完善的用户认证与权限
- 任务后台队列与消息通知
- Docker 一键部署
- 可视化实验看板
- 更强的云端管理能力
