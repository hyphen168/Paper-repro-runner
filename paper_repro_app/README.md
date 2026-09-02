# 论文复现助手（最终成品版）

这是一个面向“论文代码复现”的轻量本地应用，目标是让用户在自己的电脑上输入论文链接，并通过用户自有的云服务器完成代码复现、依赖安装和脚本验证。它的设计思路是：

- 本地应用负责任务编排、页面交互、日志展示
- User-owned cloud server 负责真实计算与代码执行
- 数据和任务记录保留在用户本机，云端只做重计算
- 整个系统尽量做到轻量、可安装、可重复使用

## 1. 产品定位

该项目不是传统单机脚本，而是一种“控制端 + 执行端”的工程化应用：

- 控制端：Streamlit 用户界面
- 执行端：SSH 远程云端运行环境
- 本地存储：SQLite 任务库
- 输出管理：日志和结果产物保存在用户本机

它适合用于：

- 论文链接转代码仓库判断
- 自动生成复现任务
- 远程代码拉取与依赖安装
- 结果状态与日志管理
- 适合进一步扩展成真实论文复现平台

## 2. 核心功能

- 输入论文链接
- 自动识别 GitHub/GitLab/Hugging Face 等代码仓库候选
- 允许用户填写云服务器地址、SSH 私钥、用户名和工作目录
- 本地保存任务记录和状态
- 远程执行包括：拉代码、安装依赖、验证项目、记录日志
- 自动收集任务产物到用户本机目录
- 开箱即用的桌面启动脚本与快捷方式

## 3. 技术栈

- Python 3.10+
- Streamlit：本地轻量交互界面
- SQLite：本地任务管理
- Paramiko：SSH 远程执行
- requests + BeautifulSoup：网页与仓库链接识别
- PyYAML：配置读取
- pytest：回归验证

## 3.1 自动环境诊断与适配

为了减少“代码仓库复现时的环境调试成本”，本应用在云端执行前会优先做以下自检：

- 检测 Python 版本是否与仓库兼容
- 识别是 `requirements.txt`、`environment.yml`、`pyproject.toml` 还是 `Dockerfile`
- 判断是否存在 CUDA / GPU 依赖
- 依据环境类型自动选择 `conda`、`venv` 或 `docker` 路径
- 将安装和验证步骤整合进同一条流水线脚本，避免每一步单独 SSH 失去环境上下文

这使得项目更接近真实的“论文复现平台”，而不是仅仅把命令堆在一起。

## 4. 架构说明

本项目采用“本地控制 + 云端执行”的分层架构：

- 本地：任务提交、状态展示、配置管理、日志展示
- 云端：代码拉取、环境创建、依赖安装、脚本验证
- 用户数据：保留在用户本地目录
- 远程凭据：保存在用户家目录，不写进仓库

## 5. 一键启动（推荐）

在 Windows 上直接双击桌面快捷方式：

- `Paper Repro Runner`

这个启动项已经使用赛博风格图标，并且在启动后会自动打开默认浏览器跳转到：

```text
http://127.0.0.1:8505
```

双击后会自动执行：

- 创建 `.venv`
- 安装 `requirements.txt`
- 启动 Streamlit 应用
- 打开浏览器访问页面

默认浏览器地址：

```text
http://127.0.0.1:8505
```

## 6. 命令行启动

```bash
cd paper_repro_app
python -m pip install -e .
python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8505
```

## 7. 目录说明

```text
paper_repro_app/
├── app.py                     # 主界面
├── start_app.py              # 一键启动脚本
├── start_app.bat             # Windows 启动入口
├── create_desktop_shortcut.py  # 桌面快捷方式生成脚本
├── requirements.txt          # 依赖列表
├── pyproject.toml            # 包入口配置
├── README.md                 # 项目说明
├── paper_repro_app/
│   ├── __init__.py
│   ├── __main__.py
│   ├── database.py
│   ├── paper_parser.py
│   ├── remote_runner.py
│   ├── config_store.py
│   ├── artifacts.py
│   └── data/
├── tests/
│   └── test_basic.py
├── docs/
│   ├── product-launch-record.md
│   └── pipeline-upgrade-log.md
└── .venv/                    # 本地虚拟环境（首次启动自动创建）
```

## 8. 交付说明

本项目已经完成最终成品版的工程收口，除了可运行代码外，还包含一套适合展示和外部反馈收集的交付材料：

- `docs/requirements-analysis.md`：需求分析与产品规划说明
- `docs/final-delivery-package.md`：最终交付说明与使用方式
- `docs/product-launch-record.md`：迭代记录，适合回顾过程
- `docs/pipeline-upgrade-log.md`：流水线增强与架构升级说明

这些文档适合：

- 提交给对接人员审阅
- 用作 GitHub 展示页的附件材料
- 作为项目说明和反馈收集入口
- 给面试官展示项目设计思路与工程落地过程

## 9. 使用流程

1. 双击启动器或运行命令启动应用
2. 填写论文链接
3. 填写或修正代码仓库候选
4. 填写云服务器信息（IP、用户名、SSH 私钥）
5. 选择运行环境（conda / venv / docker）
6. 提交任务
7. 在云端执行拉代码、安装依赖、脚本验证
8. 查看日志和任务状态
9. 所有产物保存在本地目录

## 10. 重要注意事项

- 不要将 SSH 私钥提交到 GitHub 仓库
- 本地数据目录保留在用户自己的机器里
- 云端仅用于执行工作，不承担本地数据存储
- 真实论文代码可能需要不同环境，项目已预留 conda / venv / docker 的扩展入口

## 11. GitHub 提交准备

如果要提交到自己的 GitHub 仓库，请确保：

- `.venv` 不要提交
- 密钥与配置不要提交
- 仅保留源代码、脚本、README 和文档

建议命令：

```bash
git init
git remote add origin https://github.com/hyphen168/Yolov5m-NEU-DET.git
git add .
git commit -m "feat: final product version of paper reproduction app"
git push -u origin main
```

如果分支不是 main：

```bash
git branch -M master
git push -u origin master
```

## 12. 项目价值

这个项目体现了以下工程能力：

- 本地应用与远程执行分离
- 任务状态管理
- 云端执行脚本
- 生产化的启动器与部署思路
- 用户数据本地化
- 轻量化交付能力

它可以作为一个真实的作品展示，也可以继续扩展成更完整的“论文复现平台”。
