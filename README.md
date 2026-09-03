# Paper Repro Runner

一个面向“论文复现”场景的产品化工程应用，核心目标是把“论文链接 → 代码定位 → 环境诊断 → 云端执行 → 结果分析 → 报告输出”整合成一套更像真实产品的工作流。

这个仓库同时保留了工业视觉基线能力，并在 `paper_repro_app/` 中封装了一套成熟度更高的论文复现控制台，用于演示、项目展示、GitHub 交付和面试表达。

## 1. 项目定位

这不是单纯的论文代码脚本，而是一个“本地控制端 + 云端执行端”的研究型产品：

- 本地端：任务提交、日志查看、环境配置、报告输出
- 云端端：拉取代码、安装依赖、执行验证脚本
- 智能层：自动诊断环境、分析创新点和风险
- 交付层：Markdown / JSON / 展示页 / 项目总结

## 2. 关键能力

- 论文链接输入与代码仓库候选识别
- 自动环境诊断：Python 版本、依赖类型、CUDA/GPU 需求
- 适配 conda / venv / docker 等多种工作流
- 本地任务存储与日志回流
- 远程 SSH 执行与云端计算协同
- 创新点与风险分析
- 自动生成报告和对比表
- 同网段移动端访问支持
- 赛博风格产品展示界面

## 3. 核心目录

```text
industrial-vision-repro/
├── README.md
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── data/
├── docs/
│   ├── product-showcase.html
│   ├── deployment-guide.md
│   ├── requirements-analysis.md
│   ├── final-delivery-package.md
│   └── final-product-version.md
├── experiments/
├── notebooks/
├── scripts/
│   ├── start_release.py
│   ├── start_release.bat
│   ├── evaluate.sh
│   ├── export.sh
│   └── train.sh
├── src/
│   └── industrial_vision/
├── paper_repro_app/
│   ├── app.py
│   ├── start_app.py
│   ├── requirements.txt
│   ├── README.md
│   ├── create_desktop_shortcut.py
│   └── paper_repro_app/
├── tests/
└── .gitignore
```

## 4. 一键启动

推荐方式：

```bash
python scripts/start_release.py
```

此脚本会自动：

- 创建项目虚拟环境
- 安装根项目依赖与应用依赖
- 启动 Streamlit 论文复现控制台
- 自动打开浏览器
- 输出本机与局域网访问地址

Windows 用户也可直接双击：

```text
scripts/start_release.bat
```

## 5. 手动启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r paper_repro_app/requirements.txt
streamlit run paper_repro_app/app.py --server.address 0.0.0.0 --server.port 8505
```

Windows：

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r paper_repro_app/requirements.txt
streamlit run paper_repro_app/app.py --server.address 0.0.0.0 --server.port 8505
```

## 6. SSH 自动配置（推荐）

如果你要连接远程云服务器，推荐先生成一个稳定的 SSH alias，而不是每次手动重复填写命令。

```bash
python scripts/setup_ssh_profile.py \
  --alias papercloud \
  --host connect.cqa1.seetacloud.com \
  --user root \
  --port 12680 \
  --key ~/.ssh/id_ed25519
```

也可以直接从原始 SSH 命令生成：

```bash
python scripts/setup_ssh_profile.py --target "ssh -p 12680 root@connect.cqa1.seetacloud.com -i ~/.ssh/id_ed25519"
```

生成后，可在控制台面板中直接填入 `ssh papercloud` 或在 Terminal 中一键测试连接。

## 7. 后台运行日志与错误快速定位诊断

应用内置了结构化日志轮转系统（`paper_repro_app/logs/app.log`）与智能日志分析诊断引擎，支持每次调试或处理报错时**秒级精准定位错误点**：

1. **命令行快捷分析**（直接在终端运行）：
   ```bash
   python scripts/diagnose_logs.py
   ```
   * 自动识别系统最新的失败任务与报错行
   * 精确归类错误类型（SSH 认证断开、Conda 命令缺失、pip 镜像超时、Git 克隆超时、CUDA 显存溢出等）
   * 高亮定位引发崩溃的关键代码/日志片段，并输出直观的根因与修复建议

2. **UI 大屏面板实时诊断**：
   在 Streamlit 面板的“最近任务与错误定位诊断”栏目下，每个失败的任务都会自动挂载专属的 **`🔍 错误定位与根因诊断`** 展开卡片，方便一键定位排查。

```bash
python scripts/setup_ssh_profile.py \
  --alias papercloud \
  --ssh-command "ssh -p 12680 root@connect.cqa1.seetacloud.com -i ~/.ssh/id_ed25519"
```

这样之后就可以直接用：

```bash
ssh papercloud
```

它会自动写入 `~/.ssh/config`，并且优先使用标准 SSH 配置文件，而不是在项目里硬编码私钥或临时凭证。

## 7. 访问方式

本机访问：

```text
http://127.0.0.1:8505
```

同一局域网访问：

```text
http://<你的电脑IP>:8505
```

## 7. 产品展示页

可直接打开：

- [docs/product-showcase.html](docs/product-showcase.html)

这是一个赛博风格的展示型产品页，适合：

- 项目介绍
- 演示汇报
- GitHub 展示页截图
- 与客户或导师沟通

## 8. 试用反馈问卷

首次跑完一篇完整论文复现流程后，可向测试用户收集反馈。文字版问卷已准备好：

- [docs/user-feedback-questionnaire.md](docs/user-feedback-questionnaire.md)

该问卷包含：

- 是否同意将反馈发送到邮箱 gong-xiao-hong@qq.com
- 使用感受
- 不合理之处
- 建议
- 是否愿意付费使用

同时，应用内也集成了同一套反馈表单，便于在界面中直接记录和收集。 

## 9. 部署与交付文档

- [docs/deployment-guide.md](docs/deployment-guide.md)
- [docs/requirements-analysis.md](docs/requirements-analysis.md)
- [docs/final-delivery-package.md](docs/final-delivery-package.md)
- [paper_repro_app/README.md](paper_repro_app/README.md)

这些文档能帮助你把项目包装成更完整的产品交付包。

## 9. 适用场景

- 科研论文尝试复现
- 项目成果展示
- 面试/汇报素材准备
- GitHub 作品提交
- 本地控制 + 云端计算协同

## 10. 交付建议

如果你准备推到 GitHub 或对外展示，建议保留：

- README
- 项目总结文档
- 产品展示页
- 部署指南
- 应用代码与测试

建议不提交：

- `.venv`
- SSH 私钥
- 用户云端配置
- 本地敏感日志

## 11. 运行验证

已完成基本验证：

```bash
pytest -q
```

当前状态：测试通过，项目代码与文档结构均可稳定使用。

## 12. 结论

这个项目已经从单纯的工业视觉脚手架，升级成了一个更接近“真实产品”的研究复现系统：

- 具备本地控制端
- 具备云端执行能力
- 具备环境自适应逻辑
- 具备分析与报告输出
- 具备产品展示和交付价值

如果你一直追求“做成一个能拿去展示、能拿去交付、能拿去面试”的项目，这一版已经基本达到了目标。
