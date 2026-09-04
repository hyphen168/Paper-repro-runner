# 论文仓库形态→默认适配配方（框架模板库专家报告）

## 决策

**总判定**：自动适配按三层知识命中，顺序固定：①记忆层（同仓库秒配，优先）→②模板族层（本文主产，按关键词+文件探针分类）→③通用启发（AST 依赖扫描+入口评分，已存在）→④人工 run 命令权威兜底。模板库只存"形态特征与配方"，不存任何 URL；数据集一律走现有注册表/用户 data_config/仓库自下载，模板仅标注数据形态与消费方式。全部中文、无 emoji。

**1) 模板族表（10 族+通用 fallback 行）**，字段：入口模式/数据集惯例/参数注入/依赖特点与坑。

| 族（真机案例） | 入口模式 | 数据集惯例 | 参数注入 | 依赖特点与坑 |
|---|---|---|---|---|
| yolov5/ultralytics 系（④） | 顶层 train.py（推理 detect.py）；新版 ultralytics 无顶层入口，走包 CLI yolo train | coco 风格 yaml（train/val 指向 images/labels）→ data_config 直灌 | argparse 尾缀 --weights/--epochs/--batch-size/--imgsz，auto 加 --data | 有 requirements；坑：默认 --weights 从 GitHub release 下载，不可达须 --weights "" 从头训；2024 版代码 import ultralytics 需补装；产物 runs/train/exp*/results.csv 可收集 |
| torchvision 分类 zoo（② hubconf 型） | 纯 zoo 无训脚本，仅 hubconf.py 权重入口 | torchvision 内置集（仓库代码内下载） | 无可注入 | 依赖轻；坑：无训练代码 → 判 zoo-only 明示"仅权重加载，不含训练"，禁 auto_run，引导换可训练实现 |
| kuangliu 式 CIFAR（⑤） | 顶层 main.py + models/ 子包 | CIFAR10 download=True，root 常为 data/ | 仅 --epochs 等；模型选择=改代码注释 | 无 requirements；坑：模型不可命令行选 → 判"需改源码选模型"不适配 auto，明示并推荐带 --arch 等价仓 |
| akamaster 式 ResNet（①） | trainer.py（非 train.py/main.py），--arch resnet20/56 | CIFAR10 内置下载，root 在 data/ | --arch/--epochs/--lr 尾缀 | 无 requirements → 依赖步骤需自动补装 CUDA torch；坑：入口名非常规需纳入候选并加 --arch 分；指标仅终端 Test accuracy 行需正则 |
| pytorch/examples 子目录（③） | 深层子目录 main.py（mnist/main.py、imagenet/main.py） | 子目录自管理（MNIST download=True 等） | 进入子目录后尾缀注入 | 子目录依赖独立；坑：monorepo 须先列子目录供确认任务目录，不能只找顶层 |
| HF transformers 训脚本 | examples/pytorch/*/run_*.py（run_glue 等） | --dataset_name 从 HF Hub 拉，或本地 --train_file | --model_name_or_path/--dataset_name/--output_dir/--per_device_* 尾缀 | 锁 transformers/datasets 版本；坑：境外模型数据源需 HF_ENDPOINT 镜像开关（配置项非硬编码 URL）；指标在 trainer_state.json/日志 |
| timm 分类 | 顶层 train.py/validate.py | --dataset torch 内置下载，或 --data-dir ImageFolder 根 | --model/--epochs/--batch-size/--lr；--output 指产物目录 | 依赖 timm 与 torch 匹配；坑：新 torchvision 下旧模型名漂移；产物 model_best.pth.tar 需补收 .pth |
| GAN 系（PyTorch-GAN，DCGAN 推演②） | 子目录 xxx/xxx.py（dcgan/dcgan.py） | --dataroot 消费 raw/tar-dir env 根目录或仓库自下 | --dataset/--dataroot/--niter 尾缀 | 顶层无 requirements → 自动补 CUDA torch；坑：多 GAN 子目录按目录名定任务；netG/netD.pth 与 images/*.png 需补收集；无官方量化表 → 报告 N/A 口径 |
| mmdet 系（检测非 yolo） | tools/train.py <config.py>，config 即参数面 | coco 结构目录落盘到 config 内 data_root | 改 config 或 --cfg-options 覆盖 | mmcv/mmdet 与 CUDA 版本强耦合，CUDA 轮子不在 PyPI；坑：heavy 不自动装，wheel 源走 registry 配置或引导贴 README 安装命令；config 非 argparse |
| 自定义单文件（通用启发） | 任意顶层 .py（train/detect/predict/main/app/trainer…） | 无惯例：--data 目录、内置下载或 raw env | 尾缀注入 + PAPER_REPRO_DATA_CONFIG/raw env 消费 | AST 依赖扫描兜底；坑：文件名无约定时靠 --help 命中训练标志评分定入口 |
| 通用 fallback（未归类） | 入口评分：文件名权重 + --help 含 --arch/--epochs/--data/--dataset/--config | raw/tar-dir env 兜底（dataset_discovery 已出 raw 分支） | run 模式手填命令权威覆盖 | 无；坑：多候选等权不许静默猜 → 输出结构化中文指引 |

**2) 模板落点（决策）**：内置代码常量表 repo_templates.py 的"关键词→族"只做本地初筛（仓库名/README 词，复用 AutoRepoDatasetCrawler 的 evaluate_and_rank 结果上下文）；定稿靠云端探测联动——clone 后 ModelDiscovery 扫顶层+固定子目录（examples、dcgan 类、transformers run_*.py、tools/train.py）文件清单，与族 markers（hubconf.py/trainer.py/configs/train.py 存在性、requirements 含 ultralytics 等）比对，返回 family、入口候选评分、zoo_only、unsuitable_reason。两段式保证识别失败也有据可查。URL 一律不入库。

**3) 覆盖率衡量与降级**：口径=按族分组统计 auto 命中率（成功任务数/尝试数，TaskStore 按规范化 owner/repo 聚合）、zoo/需改码提示准确率、fallback 使用率，落后族优先补条目。降级链=记忆→族模板→入口评分→run 命令；zoo-only（②类）与需改码（⑤类）均禁 auto_run，明示"该仓库无训练代码/模型选择需改源码"并给换仓指引，识别不出时给"候选入口+中文理由+粘贴 README 训练命令"按钮式引导，绝不向用户暴露 traceback 等技术细节。

**4) 维护回填流程**：新仓库人工确认真跑通后，成功页提供"记住此仓库适配方式"→ 生成草稿条目（关键词/入口/参数/数据形态/坑）写 ~/.paper_repro_app/template_drafts.json → 人工 review（≥2 真实仓库验证、无 URL、中文无 emoji）后合入 repo_templates.py 常量；用户级快速新增/覆盖写 ~/.paper_repro_app/templates_user.json（加载优先于内置、免改代码）；既有 DB 成功任务历史自动提炼为记忆层条目，无需人工。

## 可执行变更

1. 新增 paper_repro_app/repo_templates.py：FAMILIES 常量（上表 11 行：id/关键词/markers/入口规则/参数注入/data_role/坑）+ classify_by_keywords(repo_url、repo 名) + match_by_probes(文件清单)；纯函数无网络无 I/O；单测覆盖 10 族正例与负例。data_role 只取枚举：coco_yaml、raw_dir、repo_self_download、hf_dataset、imagefolder。
2. 新增 paper_repro_app/repo_memory.py：规范化仓库标识（owner/repo）+ 查询 TaskStore 最近成功任务（repo_url/run_command/data_config/host/remote_workdir/status=success 均已在表），输出预填配方与 tune 默认值，实现同仓库二次运行秒配、换机仍生效（云端目录按仓库名哈希隔离已支持）。
3. 改 model_discovery.py build_remote_script：候选由固定四名改评分制（顶层 *.py 文件名权重 + --help 命中训练标志加分）；加固定子目录与特殊文件探针；payload 增 family/zoo_only/unsuitable_reason/候选清单及原因；run_step 降级安全检查的入口循环候选表同步扩。
4. 云端 model 步定稿后将建议命令与族名回传 UI 预填（不再只认 train.py+--data 单条）；tune 面板按族默认尾缀模板（yolov5 给 batch/imgsz/epochs，CIFAR 族给 --arch/--epochs）。
5. app.py 呈现"族判定卡"：族名、可训练性、依据、数据形态说明；zoo/需改码类给指引与换仓建议；fallback 给候选入口按钮与"粘贴 README 训练命令"引导；新增"记住适配方式"按钮写草稿。
6. 依赖与镜像：族内不存源地址；HF_ENDPOINT、mmcv wheel 源等作为 registry/配置可编辑项（config_store 通道，无明文密码）。mmdet 族命中时提示依赖 heavy 不自动装。
7. 度量与回归：新增 report_templates_coverage.py（本地只读查询输出各族命中/降级/zoo 计数）；全量保持 pytest 88 基线全绿、AppTest 0 异常、不引入新框架；全部新增文案中文无 emoji、无 URL 常量、无明文口令。
