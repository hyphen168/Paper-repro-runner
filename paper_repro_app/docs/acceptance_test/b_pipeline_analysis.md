# 软件链路分析简报：三篇代表论文全自动链路逐篇推演

范围：以 lead 裁决的代表候选池（a_papers 产出后由 lead 终选）推演——① ResNet-20/56 CIFAR-10（He et al. 2016，仓库代表 kuangliu/pytorch-cifar，官方数值来自论文 Table 2：20 层 8.75% 错误、56 层 6.97%）；② DCGAN（Radford et al. 2016，仓库 eriklindernoren/PyTorch-GAN，CIFAR-10 官方直链 cifar-10-python.tar.gz）；③ YOLOv5（ultralytics/yolov5，coco128 演示集）。依据代码事实：remote_runner.build_pipeline 十步、DatasetDiscovery/ModelDiscovery 云端自包含脚本、collect 载荷与 comparison_table/report_generator 本地链路、dataset_lead_spec（未落地）。URL 可达性三级标注：confirmed=本软件真机跑过；known=已知域名常规可达；verify-on-cloud=执行时云端 HEAD 探针兜底。

## 决策

总判定：裸软件现网形态只能直跑通 ③；① ② 各有"入口识别 + 数据集形态 + 指标落点"三处结构性断点，其中两处（无 requirements 仓库缺 torch、tar 包在 py3.10 环境 extractall(filter='data') 崩溃）是全局性断点，会连坐所有非 yolov5 型仓库。因此本次验收必须按"先落地最小 P0 补丁组，再三机并行逐篇全跑"推进，不可裸测三篇（裸测只能证明 yolov5 型通用性，违背"不要只验证要全程跑通"的目标）。

### 1) 逐篇链路推演表

#### ① ResNet-20/56 CIFAR-10（kuangliu/pytorch-cifar）

| 环节 | 推演 | 判定 |
|---|---|---|
| clone | github.com/kuangliu/pytorch-cifar（数 MB 纯码）；known，ghfast.top 自动备用 | 直跑 |
| conda | py3.10 环境可用；仓库仅需 torch/torchvision，无版本死锁 | 直跑 |
| requirements/setup | 仓库无 requirements.txt、无 setup.py → install 步骤空转；AST 扫描命中 torch/torchvision 属 heavy 只提示不装 → 运行必 ModuleNotFoundError | 需小补丁 P0：dependency 步骤对 heavy_hit 含 torch 且 torch 不可用时自动装 CUDA torch（复用 install_req_file 的 cu128→cpu 两源逻辑） |
| 数据集 | 训练代码内部 torchvision CIFAR10(root='./data', download=True) 硬编码，cs.toronto.edu 国内 verify-on-cloud（known 高风险）；官方 URL 直链经 URL 分支下载 → 落盘 tar.gz → py3.10 下 extractall(filter='data') 抛 TypeError，且引擎找不到 YOLO 结构直接 SystemExit | 需小补丁 P0：tar 提取换 py3.10 安全循环；增加 raw/tar-dir 兜底（见 §3） |
| 入口识别 | 入口为 main.py（argparse --arch/--epochs），不在 train.py 候选内，且无 --data → auto 模式 exit 65 | 需 run 模式（run_command），P1 再扩 ModelDiscovery |
| 参数注入 | run 模式命令原样执行，argparse 尾缀天然可用 | 直跑 |
| 指标落点 | 无 results.csv，仅终端每轮测试行 "Accuracy of the network on the 10000 test images: X%" | 需小补丁：collect 正则兜底（§2） |
| 论文对比 | Table 2：20 层 8.75%、56 层 6.97% 错误（CIFAR-10 test，arXiv 1512.03385） | 报告需填 paper 列 |
| 预算 | resnet20 160 epochs（每轮约 8-12s，warm 缓存后约 25-35 分钟）；先 20 层后 56 层 | 可行（上限附近） |

verdict：需小补丁（P0 三个 + run 模式使用）。注意该仓库近年重构为 torchvision 风格 ResNet18/34/50 名单，clone 后须 python main.py --help 核对 --arch 是否含 cifar 版 20/56；若无则换 akamaster/pytorch_resnet_cifar10（README 自带 Table2 数值对照）。

#### ② DCGAN（PyTorch-GAN, CIFAR-10）

| 环节 | 推演 | 判定 |
|---|---|---|
| clone | eriklindernoren/PyTorch-GAN（全仓库含几十个 GAN 文件夹，代码量中等）；known；此前真机 clone/env/降级已通 | 直跑 |
| conda | py3.10 无冲突 | 直跑 |
| requirements/setup | 顶层无 requirements.txt（verify-on-cloud）→ 同①：torch/torchvision 不会被自动补装 | 需 P0 同一补丁 |
| 数据集 | 官方直链 https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz（known，verify-on-cloud；失败手动切 hf-mirror 镜像）；tar.gz 在 py3.10 崩溃 + 引擎只认 YOLO 结构（无 images/labels） | 需 P0 同上两个补丁 |
| 入口识别 | 入口是 dcgan/dcgan.py（argparse --dataroot/--dataset/--niter），ModelDiscovery 三候选全 miss | 需 run 模式；P1 扩发现 |
| 参数注入 | --dataroot 直接消费引擎 env（raw 兜底后 PAPER_REPRO_DATA_CONFIG=datasets 父目录，torchvision 见 datasets/cifar-10-batches-py 即免下载） | raw 兜底落地后直跑 |
| 指标落点 | 无 csv；终端逐 batch 打 Loss_D/Loss_G/D(x)/D(G(z))；产物 images/*.png；权重 netG/netD.pth 不在 collect 名单 | 需 P0 正则兜底；P1 artifacts 增补 .pth |
| 论文对比 | 原论文在 ImageNet/LSUN 上训练，无逐项量化指标表（不符合硬约束 5 的"官方数值+出处"），且与 CIFAR-10 口径不同 | 报告 paper 列标 N/A + 口径说明；正式验收若坚持强对比建议换含官方数值候选 |
| 预算 | niter 100、batch 64（约 782 步/轮），4090 上约 10-20 分钟 | 可行 |

verdict：需小补丁（P0 两个 + run 模式 + 正则）。

#### ③ YOLOv5 + coco128

| 环节 | 推演 | 判定 |
|---|---|---|
| clone | ultralytics/yolov5，confirmed（34367 机 safe 全链路 success），ghfast 备用 | 直跑 |
| conda/install | requirements.txt 存在 → install_req_file 探测到 GPU 无 CUDA torch 时自动装 cu128/cpu；torch 行被保护不二次升级；yolov5 对 py3.10/torch2 兼容 | 直跑 |
| 数据集 | data_config 填 https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip（zip 分支安全，不触发 tar bug；known，verify-on-cloud，失败手动加 ghfast.top 前缀）；引擎自动生成 paper_repro_auto.yaml（train2017/val2017、nc=80） | 直跑（引擎对 zip 无补丁依赖） |
| 入口识别 | train.py 命中且 --help 含 --data → auto_command 正确 | 直跑 |
| 参数注入 | tune 模式 yolov5 风格尾缀 --batch-size/--epochs/--imgsz/--device 追加；注意默认 --weights yolov5s.pt 会从 github release 自动下载（verify-on-cloud），不可达时切 run 模式加 --weights "" 从头训 | 直跑（含一个验证点） |
| 指标落点 | runs/train/exp*/results.csv 末行含 metrics/mAP_0.5、mAP_0.5:0.95、precision、recall 及各 loss → collect 的 map/precision/recall/loss token 全命中；best.pt/last.pt/png 均入 artifacts | 直跑 |
| 论文对比 | 官方数值是 COCO val2017 口径（README Models 表，数值随 tag 变化：v6.1 与 v7.0 不同），coco128 属演示口径 → 不能直接对比，报告用"口径说明 + 云端 clone 后读 README 表回填 paper 列并记 tag" | 需口径说明，非代码补丁 |
| 预算 | 50 epochs × 128 图，约 8-15 分钟 + 数据下载 | 可行 |

verdict：可直跑（0 补丁，仅需选 URL 直链与一处权重可达性验证）。

### 2) 指标收集兼容性（collect 九项 vs 三篇输出格式）

collect 现状：仅扫 repo 内 results.csv/metrics.csv/results.json/metrics.json，按 token（map/precision/recall/f1/accuracy/acc/loss）抽末行/末条；全库抓 best.pt/last.pt 与 png/jpg（≤50）。覆盖矩阵：③全命中（6/9 项由 csv 覆盖，epoch 列与 F1、吞吐未收）；① ② 全部落空。

| 九项 | ③yolov5 | ①resnet | ②dcgan |
|---|---|---|---|
| top-1 acc/错误率 | 无此口径 | 需正则 | 无 |
| precision / recall | csv 覆盖 | 无 | 无 |
| mAP@0.5 / mAP@0.5:0.95 | csv 覆盖 | 无 | 无 |
| F1 | 需正则（val 汇总行） | 无 | 无 |
| 最终 loss（train/val） | csv 覆盖（4 列 loss 并存） | 正则取末轮 | 正则取末批 Loss_D/G |
| 吞吐/每轮耗时 | 日志 it/s 需正则 | epoch Time 需正则 | 无（图片产物代收敛证据） |
| 产物 | best.pt/last.pt/results.png 覆盖 | 需补 best.pth/checkpoint.pth | 需补 .pth（当前只收 best.pt/last.pt） |

缺失兜底（建议正则与键名，建议放在本地结果整理阶段对完整日志做，因 full logs 已回传；云端 collect 也可加）：
- 键 accuracy：`Accuracy of the network on the 10000 test images:\s*(\d+\.?\d*)\s*%`（末次命中值，同时派生 error=100-accuracy）；备选 `Best acc` / `acc\s+([\d.]+)%`。
- 键 loss_d/loss_g：`\[(\d+)/(\d+)\][^\[]*Loss_D:\s*([\d.eE+-]+)\s+Loss_G:\s*([\d.eE+-]+)`（取末次）；收敛证据键 d_x/d_gz：`D\(x\):\s*([\d.]+)\s+D\(G\(z\)\):\s*([\d.]+)\s*/\s*([\d.]+)`。
- 键 throughput：`(\d+\.?\d*)\s*(?:it/s|images/s|FPS)`；键 epoch_time：`Time\s+([\d.]+)`。
- yolov5 F1：`all\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+[\d.]+\s+[\d.]+` 不推荐（列序易漂移），以 results.csv 为准即可。
报告生成现状：comparison_table 的 paper 列恒为"待填充"，无官方数值注入机制——本次验收报告由测试方把 §1 出处数值写入对比行（ResNet 用 Table 2、yolov5 用云端读到的 README Models 表并记 commit tag、DCGAN 标 N/A 口径），属 P1 本地补丁（expected_metrics 映射或 UI 文本框），不阻塞云端链路。

### 3) 数据集规范未落地的应对（顺序建议）

推荐顺序：先落地"最小 P0 子集"再开跑，而不是等 P0 多候选+reason_code 全套，也不是裸测。
依据：① ② 需要的数据集恰好同时踩中"tar 包 py3.10 崩溃"与"非 YOLO 结构被引擎拒绝"两个已知缺陷；不修这两点，run 模式会在 dataset 步骤 fatal 退出，训练根本启动不了。而用户 URL 多候选/镜像派生/注册表（spec 的其余 P0/P1）本次用不到——三篇 URL 均为单一直链、已知可达，留到下次迭代。
最小落地清单（全部在云端自包含脚本内，不动本地签名）：
1. dataset_discovery.build_remote_script：删两处 extractall(filter='data')（URL 分支与 YAML download 分支），换成 py3.10 兼容的逐成员安全提取（沿用 spec 的 zip-slip/闸门规则）；zip 分支不动。
2. 增加 raw/tar-dir 兜底：用户显式 URL 下载解压后若找不到 YOLO 结构，不 SystemExit；改为输出环境变量 export PAPER_REPRO_DATA_CONFIG=<解压根父目录绝对路径>（供 --dataroot/root 类参数消费）、打印原始目录提示与 payload {raw: True, dataset_root}，exit 0；仅限"用户显式填 URL"分支，自动寻源仍走原 degrade，避免误下大文件。
3. reason_code 兜底字段（spec 第五节 degrade 兜底字典），P1 可后置。

### 4) 每篇实施清单（P0 必须 / P1 建议 / 命令级验证要点）

通用 P0（先做，一提交完成）：G1 dependency 步骤 heavy_hit 命中 torch/torchvision 且 torch_cuda_ok 失败时自动装 CUDA torch（源 cu128→cpu，420s 超时，装后重扫一次 missing）；G2 数据集 tar py3.10 修复 + raw 兜底；G3 collect/本地日志正则兜底（§2 三组正则）。
通用 P1：ModelDiscovery 候选扩 main.py 及 README 命令抽取（保守评分，仅当含 --epochs 且命中 CIFAR10/ImageFolder/--dataset/--arch）；artifacts 增补 .pth/.ckpt/.onnx；comparison 支持 expected_metrics；PIP_CACHE_DIR 在系统盘 <8G 时切数据盘。

① pytorch-cifar：
- P0：G1+G2+G3；run 模式提交；data_config=官方 CIFAR tar 直链。
- run_command：`if [ -n "${PAPER_REPRO_DATA_CONFIG:-}" ]; then rm -rf data; ln -sfn "${PAPER_REPRO_DATA_CONFIG}" data; fi; python main.py --arch resnet20 --epochs 160`
- 验证要点：clone 后 `python main.py --help` 确认 --arch 有 resnet20/56（无则换 akamaster 仓库）；dataset 步骤日志出现解压完成与 raw 目录提示；运行日志末轮 Test accuracy 落盘且被正则提取（resnet20 期望 90%+，56 层为第二跑 stretch 目标 93%±）；`find datasets -maxdepth 1 -type d` 含 cifar-10-batches-py；任务 JSON 中 metrics.accuracy 非空。
② PyTorch-GAN dcgan：
- P0：G1+G2+G3；run 模式；data_config 同上直链。
- run_command：`python dcgan/dcgan.py --dataset cifar10 --dataroot "${PAPER_REPRO_DATA_CONFIG}" --niter 100 --batchSize 64`
- 验证要点：cloud HEAD 探针先测 cs.toronto.edu（不可达则换 hf-mirror 镜像直链填入 data_config 重试）；无 "Downloading" 即命中本地缓存；末批 Loss_D/G 与 D(x)≈0.5 收敛信号被正则捕获；collect artifacts 出现 images/*.png；权重存证建议 run 后追加 scp/或补 .pth 收集（P1）。
③ yolov5+coco128：
- P0：无代码补丁；run_mode=tune（framework=yolov5，epochs=50、batch=16、imgsz=640），data_config=coco128 GitHub release 直链。
- 验证要点：`curl -sIL <coco128-url> | head -3` 与 `curl -sIL https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5s.pt | head -3` 云端可达性；dataset 步骤生成 paper_repro_auto.yaml；训练日志出现 Epoch/mAP 行；`ls runs/train/exp*/results.csv` 存在；collect 摘要行含 mAP；README Models 表数值回填对比行并记录 commit tag（口径注明 COCO val2017 vs coco128 演示集）。
- 兜底：yolov5s.pt 下载失败则切 run 模式 `python train.py --data ${PAPER_REPRO_DATA_CONFIG} --weights "" --epochs 50 --batch-size 16` 从头训练并在报告口径注明。

预算与资源：三机并行一篇一机；首轮含环境自举 3-6 分钟与依赖安装，次轮起全缓存（env 在 /root/autodl-tmp/envs、数据在 repo/datasets 均跨任务保留）；每步 command_timeout 保持默认 60 分钟可覆盖 resnet160 轮；注意 30G 系统盘与 pip 缓存占用，装完 torch 后 `df -h /` 确认余量（见 G 组 P1）。DCGAN 的"无官方数值"缺陷写进最终验收报告的风险与口径章节，若 lead 坚持三篇都须表格化数值对比，建议把 ② 换成含官方表值任务（如 pytorch-cifar 的 resnet56 单跑或增补第 4 类任务）——详见 Gaps。

## 可执行变更

按文件锚点列出的最小改法（无 emoji、中文、不动既有载荷键与降级标记语义）：

1. remote_runner.py dependency_step 的 heavy_hit 分支：将"仅打印提示"改为——当 heavy_hit 含 torch/torchvision 且 torch_cuda_ok 探测失败，复用 pip_install_helper 的 cu128/cpu 双源安装（timeout 420s），成功后 grep 保护重扫一次；失败才降级提示。覆盖 ① ② 无 requirements 仓库。
2. dataset_discovery.py build_remote_script：a) 两处 tarfile extractall(filter='data')（URL 直链嵌入段与 YAML download 分支）替换为 py3.10 逐成员安全提取；b) 在"用户显式 URL 且解压后无 YOLO 结构"路径插入 raw 兜底（写 env、payload 带 raw=True/dataset_root、exit 0），仅限 requested 非空分支，自动寻源分支保持原 degrade。
3. 指标正则兜底：新增 metric_parse（纯函数，解析完整日志），在 storage_utils 结果整理阶段 merge 进 result["metrics"] 后再生成 comparison_table；键名见 §2，均取末次命中。
4. （P1）model_discovery.py：候选表后追加"main.py 启发式"与 README 训练命令抽取，评分保守，只给出 reason 明确的 auto_command。
5. （P1）comparison_table/report_generator：支持每任务 expected_metrics（metric→{paper, source}），自动算 gap，paper 列不再恒为"待填充"。
6. （P1）artifacts/collect：收集名单加 .pth/.ckpt/.onnx/.npz，上限仍 50。

验收命令（每台机上人工复核一次，均为只读/无害）：`bash -n <每步脚本>` 已由既有测试覆盖；新增用例建议：构造含 tar.gz 的 data_config 最小包跑 dataset 步骤应 exit 0 且输出 raw 提示；对无 requirements 的假仓库（仅 import torch）跑 install+dependency 应自动装成 CUDA torch；用样例日志跑 metric_parse 三组正则应各提取 1 条。

## Gaps
- ① 的 kuangliu 仓库近期架构名单可能不含 cifar 版 ResNet-20/56（需 --help 实核，备选 akamaster/pytorch_resnet_cifar10）；官方 8.75/6.97 出自论文 Table 2（CIFAR-10 test），与所选仓库训练口径（epochs/增强/调度）存在 1-3 个点的合理漂移，报告需给 gap 容差。
- DCGAN 无官方量化指标表，与硬约束 5 冲突（已在正文给出取舍）。
- yolov5 官方数值随 commit tag 漂移，需云端实测回填并记 tag，报告不预写死数值。
- "九项指标"在代码与既有文档中无唯一定义，本文按评测目标分解为 9 项映射；若 lead 有既定清单请下发以对齐键名。
- 数据集镜像注册表、多候选与 reason_code 前端渲染未落地，本次不阻塞但需在下迭代补（spec 已给出实施顺序）。
- 建议第 4 类候选（NLP 分类或 ImageNet 风格 CNN，含官方表值）以覆盖非 torchvision 数据集形态与 JSON 指标格式（如 HF Trainer 的 metrics.json），提升普适性证据。

## 资源与连接
三台测试机按 lead 分配一机一篇，root 密码仅存于进程内存与 lead 侧，本报告不记录任何明文口令；连接方式沿用软件内 SSH 密码注入路径（app.py 提交时 task["password"] 内存传递、remote_runner L1/L2 自动选可达机），与本报告无涉。
