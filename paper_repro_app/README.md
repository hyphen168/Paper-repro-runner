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
- 全网智选爬虫引擎（AutoRepoDatasetCrawler）：自动解析论文并匹配 Gitee/GitHub 最优代码仓库；数据集来源以目标仓库的配置为准
- 多文章目录隔离与同一文章重置：不同论文自动独立目录存储，避免干扰；同一论文重复运行自动重置覆盖
- 允许用户填写云服务器地址、SSH 私钥、用户名和工作目录
- 本地保存任务记录和状态，SQLite 自动架构迁移（SQLiteOpenHelper）
- 远程执行包括：拉代码、安装依赖、验证项目、记录日志
- 自动复用云端 Conda/venv 与 `$HOME/.cache/pip` 缓存，已安装依赖不重复下载
- 自动识别 `train.py`、`detect.py`、`predict.py`、`main.py` 等模型入口并执行安全启动检查；选择“实际运行”并填写明确命令后，才会执行训练、验证或推理
- **自动依赖自愈**：依赖扫描（AST 解析仓库全部 import）后自动补装缺失公共包（多镜像源回退：清华 → 阿里 → PyPI）；未映射的 import 按包名逐个尝试直装，失败自动跳过不阻断；重型框架（torch/tensorflow 等）不自动乱装，检测到即给出 CUDA 版本提示
- **数据集主题相关性匹配**：自动下载前用仓库名拆词（如 Yolov5m-NEU-DET → neu/det）对候选数据集 YAML 评分，只下载匹配配置；多候选且均不匹配时明确报错引导（避免 YOLOv5 全量仓盲目下载 20GB+ 的 Argoverse）；下载前检查磁盘剩余空间与 HEAD 体积
- 数据集下载支持 308 重定向跟随与 3 次自动重试（Python 3.10 urllib 不跟随 308 的兼容处理）
- 对实际运行命令设置可配置超时，避免错误参数无限占用云端资源；默认仅做安全检查，不会擅自训练
- 数据集发现模块会在克隆后扫描当前仓库的 `*.yaml` / `*.yml` 和 README：自动选择包含 `train` / `val` 的数据集配置，优先使用声明官方下载的配置
- 训练时可自动执行当前仓库 YAML 中声明的官方数据集下载指令，支持 HTTP(S) ZIP/TAR 数据集包与仓库 Shell/Python 下载脚本；下载脚本以落盘方式独立执行，若引用上下文变量会自动注入 YAML 配置字典兜底；下载前后校验 train/val 路径，完整数据集会被复用而不会重复下载
- 自定义训练命令可使用 `${PAPER_REPRO_DATA_CONFIG}`，系统会在下载并校验完成后将自动发现的 YAML 路径注入该变量
- 自动解析常见 `results.csv`、`metrics.csv`、`results.json`、`metrics.json` 中的 mAP、Precision、Recall、F1、Accuracy 和 Loss，并记录最佳权重、图表等关键产物路径到本地任务结果
- 自动收集任务产物到用户本机目录，提供后台日志与一键根因诊断工具（log_analyzer）
- 软件封装与跨机器便携：不依赖任何本地硬编码路径，分发发给朋友或换电脑开箱即用
- 开箱即用的桌面启动脚本与快捷方式
- 小清新浅色界面：莫兰迪色系 + 柔和卡片 + 丝滑过渡动画，无功能装饰组件全部移除
- 天气粒子特效：按本机所在位置实时天气自动渲染雨/雪/云/雾/晴/雷暴粒子（IP 定位 + Open-Meteo，免费免密钥，失败自动降级）

## 3. 技术栈

- Python 3.11+
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

## 3.2 远程命令落盘执行与稳定性保障

云端流水线所有关键步骤统一采用「落盘执行」方式下发：先将脚本写入仓库目录（如 `.dep_scan.py`、`.dep_dataset.py`、`.paper_repro_download_helper.py`），再执行脚本文件，避免超长命令内联解析被截断（真实云端曾出现 `bash: line 2: syntax error: unexpected end of file` 与 `/bin/sh: import: not found` 两类截断故障）。

- **环境诊断（env）**：bash 分支结构（if/fi 配对）有完整性与回归保障；支持 conda → venv → 无 Python 时自动安装 Miniconda（清华镜像）三级兜底
- **依赖扫描与补装**：`.dep_scan.py` 落盘执行，自动发现仓库基础运行 import，并用共享 pip 缓存（`$HOME/.cache/pip`）按多镜像源顺序补装
- **数据集准备**：`.dep_dataset.py` 落盘执行仓库 YAML 扫描与官方下载；仓库声明的 Python 下载脚本若依赖上下文变量（如 `yaml['path']`），会注入兜底：独立执行时自动从声明该下载指令的 YAML 配置加载为字典（经 `PAPER_REPRO_HELPER_CONFIG` 传入），避免 `NameError`
- **结果收集**：远端输出结构化结果清单（base64 载荷），本地解析后展示指标与关键产物

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

- 检测本机 Python（3.11+，缺失时给出安装指引）
- 创建 `.venv`（拷贝过来的损坏虚拟环境自动重建）
- 安装 `requirements.txt`（依赖指纹比对，未变化时秒开；失败自动切清华/阿里镜像）
- 启动 Streamlit 应用
- 打开浏览器访问页面

默认浏览器地址：

```text
http://127.0.0.1:8505
```

## 5.1 便携分发（拷给朋友即用）

应用设计为"文件夹即安装包"：

- **应用目录纯代码**：任务库、日志、产物全部保存在用户家目录 `~/.paper_repro_app`（旧版应用目录内数据首次启动自动迁移），拷给朋友不会带走你的任务数据，升级替换文件夹不丢历史
- **依赖锁定版本**：`requirements.txt` 全部 `==` 锁定，朋友装到与你完全一致、实测可用的环境
- **一键打包**：双击 `make_dist.bat`，自动清理 `.venv`/缓存/日志等运行残留，在上级目录生成
  `PaperReproRunner-<版本>.zip` 和 `使用说明.txt`
- **朋友侧只需 4 步**：解压 → 装 Python 3.11+（仅首次）→ 双击 `start_app.bat` → 浏览器自动打开
- **换论文/换仓库不影响使用**：每篇论文独立本地目录；云端目录按 `仓库名__哈希8位` 隔离，同名不同仓库互不覆盖，同一仓库重复运行保持重置复用逻辑

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
├── start_app.py              # 一键启动引导（venv自检/依赖指纹/镜像回退）
├── start_app.bat             # Windows 启动入口
├── make_dist.py / make_dist.bat  # 一键打包分发
├── create_desktop_shortcut.py  # 桌面快捷方式生成脚本
├── requirements.txt          # 锁定版本的依赖列表
├── pyproject.toml            # 包入口配置
├── README.md                 # 项目说明
├── paper_repro_app/
│   ├── __init__.py
│   ├── __main__.py
│   ├── database.py
│   ├── paper_parser.py
│   ├── remote_runner.py
│   ├── remote_workdir.py    # 云端目录推导（哈希隔离）
│   ├── paths.py             # 统一路径（数据全在用户家目录）
│   ├── config_store.py
│   ├── artifacts.py
│   └── data/
├── tests/
│   ├── test_basic.py
│   └── test_portability.py  # 可移植性回归测试
├── docs/
│   ├── product-launch-record.md
│   └── pipeline-upgrade-log.md
└── .venv/                    # 本地虚拟环境（首次启动自动创建，分发时排除）
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
6. 选择“安全检查”或“实际运行”；实际运行时填写仓库对应的训练、验证或推理命令，并设置超时
7. 提交任务
8. 在云端执行拉代码、安装依赖、脚本验证和（如已选择）真实模型运行
9. 查看日志、指标对比表和关键产物清单
10. 所有任务结果保存在本地目录

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
