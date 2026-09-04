# 论文与数据集选型调研报告（三台 4090 真机全程复现验收）

置信标注约定：[已核实] 本仓库前次真机验证或有据可查的固定事实；[known] 知名官方直链/官方仓库固定事实；[verify] 需在执行阶段云端 HEAD 或抓取复核后定稿（父进程已确认执行阶段对所有 URL 做云端实测兜底，本报告不因此阻塞）。

## 决策

### 0. 选文标准（验收判定用）
1) 仓库为官方或活跃开源仓库，depth-1 clone 小于 150MB；2) 数据集无登录、无科学上网，体积 200MB-3GB 或自动可下小集；3) 模型在 4090D 单卡 10-25 分钟内收敛出真实数值；4) 对比数值必须有出处（论文表号或官方 README/官方仓库），且同数据集同量级才作等值对比，否则按口径说明处理。

### 1. 三篇选定总览
| 机位 | 任务族 | 仓库 | 数据集 | 论文数值出处 | 预算 |
|---|---|---|---|---|---|
| 机1 | 图像分类（CNN 残差网络） | chenyaofo/pytorch-cifar-models（备选 kuangliu/pytorch-cifar） | CIFAR-10 | He 2016 Table 6（ResNet-20 误差 8.75%） | 约 20-28 分钟 |
| 机2 | 目标检测 | ultralytics/yolov5 | COCO128（7MB 冒烟） | YOLOv5 官方 README 模型表（COCO val mAP 37.2）+ 官方 coco128 教程数值 | 约 12-18 分钟 |
| 机3 | 轻量 CNN + 多文件数据集 + 非标准入口 | pytorch/examples（mnist 子目录） | MNIST | 官方 repo README（约 99%）；LeCun 1998 论文（测试误差 0.95%） | 约 8-15 分钟（余量用于软件边界测试） |

### 2. 机1：CIFAR-10 残差网络分类（He 2016，CVPR，arXiv:1512.03385）
- 仓库：https://github.com/chenyaofo/pytorch-cifar-models （实现与论文同构的 CIFAR 窄体 ResNet-20/32/44/56/110 及 WideResNet，README 附模型库与准确率表，另有配套训练脚本目录，仓库体积约 1MB）[known]，URL 证据：仓库主页与 arXiv 1512.03385 摘要页。备选：https://github.com/kuangliu/pytorch-cifar （README 官方数值表：ResNet18 93.02%），仅在其入口/脚本缺失时启用。
- 数据集：CIFAR-10 python 版压缩包 162.6MB，训练入口由 torchvision 自动下载。[known] 官方直链 https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz （国内直连不稳定，[verify]）；兜底候选：HuggingFace 镜像 https://hf-mirror.com/datasets/uoft-cs/cifar10 [verify]；ModelScope 检索 "CIFAR-10" 数据集 ID（执行期确定）[verify]。需在云端对该直链做 HEAD 实测决定用哪条。
- 训练入口：仓库训练脚本（train 目录内，入口名需在执行期用入口识别器确认，若为通用名 train.py 则零改动）[verify]。
- 推荐规模：ResNet-20，bs128、lr0.1、SGD、weight decay 1e-4、随机裁剪加翻转（与论文一致），epoch 先 30 冒烟（约 3-4 分钟）后视速度决定 160-200 epoch。窄体 ResNet-20 参数量约 0.27M，4090D 上预估 4-8 秒/epoch，200 epoch 约 15-25 分钟。
- 论文对比数值（出处：He et al. 2016, Table 6, CIFAR-10 test error）：ResNet-20 8.75%、ResNet-32 7.51%、ResNet-56 6.97%、ResNet-110 6.43%；训练口径为 64k 次迭代（约 163 epoch）、bs128、lr 0.1 在 32k/48k 两次除 10。
- 复现目标与口径：完整 163-200 epoch 时 ResNet-20 误差落 8.7%-10.5%（即准确率 89.5%-91.3%）；若因预算截断到 120 epoch，预期误差上浮 1-2 点（lr 尚未二次衰减）。论文表值为全量训练基准，与截断运行的差距口径为"训练预算截断"，非实现缺陷；报告对比表必须注明各自 epoch 数。
- 风险标注：a) 依赖怪癖：torchvision 直连下载 CIFAR 失败时脚本无镜像参数，需软件在下载前预置压缩包到 data 目录或改用镜像源整包 [verify]；b) 入口识别：chenyaofo 仓库训练脚本路径与命名需实测，备选 kuangliu 仓库入口确定是 train.py 但其 ResNet18 为标准宽度（约 11M 参数），epoch 约 15-25 秒，需砍半 epoch，两仓库都已在上面给出回退链，不阻塞。

### 3. 机2：YOLOv5s + COCO128 冒烟（检测族，官方无独立论文，数值以官方仓库为准）
- 仓库：https://github.com/ultralytics/yolov5 （v6.0/v7.0 官方活跃仓库，depth-1 clone 约数 MB）[known]。
- 数据集：coco128（train+val 共 128 张，压缩包约 7MB），由仓库 data/coco128.yaml 声明自动下载，直链 https://ultralytics.com/assets/coco128.zip [known]，[verify] 国内可达性需云端 HEAD 实测；兜底为 gitee/ghfast 上的仓库镜像与 ultralytics assets 发布页镜像 [verify]。COCO 全量（val2017 约 19GB）明确不在本机下载范围内，只作口径参照。
- 训练入口：仓库根 train.py，coco128.yaml 在 data/ 下，入口识别与 YAML 自动下载正好命中软件既有能力（34367 机已实测 yolov5 safe 全链路成功，即本项前次验证过的能力）。
- 推荐规模：yolov5s、img640、bs64、epoch 先 3 冒烟（与官方教程一致）后视速度跑 50-100。4090D 上 128 张图每 epoch 约 5-8 秒（含验证），100 epoch 约 10-18 分钟。
- 论文对比数值与口径：
  a) 全量口径（出处：YOLOv5 官方 README "Pre-trained Checkpoints" 表，v6.0）：yolov5s 在 COCO val2017 上 mAP@.5:.95=37.2、mAP@.5=56.0。COCO128 为 1/1000 规模子集，其 AP 与全量 37.2 不可等值对比，报告中必须单列口径行。
  b) 同规模等值基准：YOLOv5 官方文档（Train Custom Data 教程）曾给出 yolov5s 在 coco128 上 3 epoch 的示例结果 P 0.543 / R 0.509 / mAP@.5 0.287 / mAP@.5:.95 0.116 [verify：执行期抓取官方 tutorial 页面留存出处]；同规模同配置复跑目标区间为各值正负 0.04（训练随机性）。该教程行若已从页面移除，则以本机同配置复跑 3 次取中位数作为基线并注明"官方教程历史数值待复核"。
  - 指标收集：yolov5 自动写 results.csv，软件解析器已有 mAP/P/R/F1 支持，属低风险项。
- 风险标注：a) 首次运行自动下载 yolov5s.pt 权重（约 14MB，GitHub 直链，[verify] 国内可达性，兜底 gitee/ghfast 镜像）；b) ultralytics.com 资产 CDN 偶发限速，需重试逻辑（软件已有 3 次重试）；c) 若云端缺 libgl/字体等系统库，训练脚本的绘图段可能报错——执行时以无绘图或关闭 plots 参数规避。

### 4. 机3：MNIST CNN（pytorch/examples/mnist，验证软件三条真实边界）
- 仓库：https://github.com/pytorch/examples （官方仓库，clone 全部约 30-50MB，[known]；实际使用 mnist 子目录，入口是 main.py 而非 train.py，正好命中"入口识别"边界）。
- 数据集：MNIST 四个 gz 文件共约 11MB，由 torchvision 自动多文件下载；torchvision 0.13 起默认镜像源为 https://ossci-datasets.s3.amazonaws.com/mnist/ [known]（已弃用 yann.lecun.com 原站），[verify] 国内可达性待云端 HEAD 实测；兜底：hf-mirror 数据集 ylecun/mnist [verify]。
- 训练命令入口：examples/mnist/main.py，默认约 14 epoch、bs64、Adam、加 dropout，无数据增强，训练与测试同脚本。
- 预计时长：4090D 上 14 epoch 约 2-5 分钟，可跑 2-3 遍（顺带验证重复运行重置与缓存复用），剩余预算做软件边界测试。
- 论文对比数值：a) 官方 repo README 声明测试准确率约 99%（README 首段，"99% test accuracy"）；b) 原论文（LeCun et al., 1998, "Gradient-Based Learning Applied to Document Recognition", Proc. IEEE 86(11)）：MNIST 测试错误率 0.95%。口径：论文为 1998 年 LeNet 系单模型最优，本仓库为现代 CNN（含 dropout）同任务无增强，两者同数据集同量级，预期准确率区间 98.8%-99.4%（误差 0.6%-1.2%）。
- 风险标注：a) 指标只在 stdout 打印（"Accuracy of the network on the 10000 test images: 99 %"），无结构化文件，正好验证软件"日志指标解析兜底"，需在执行期确认解析正则可命中；若未命中列为缺陷并回填解析规则；b) 无 train.py 仅有 main.py，入口识别器需覆盖；c) s3 源国内可达性不确定，兜底链已在数据段给出。

### 5. 候选池落选记录（附原因，留作后续轮次）
- DCGAN/WGAN（CIFAR-10）：DCGAN 原论文（arXiv:1511.06434）实验在 LSUN/ImageNet/人脸，无 CIFAR-10 官方数值；CIFAR-10 上可比数值需第三方 IS/FID 实现且 Inception 权重下载源（TensorFlow model zoo）国内不稳定；25 分钟内收敛的生成器 IS 与论文量级不可比，违反"有官方数值可对比"。建议在具备 FID 权重缓存与 90 分钟预算的后置轮启用。
- WGAN-GP（Gulrajani 2017，arXiv:1704.00028）：论文 Table 1 有 CIFAR-10 IS 值，但需约 10 万次判别器迭代，超预算一个数量级，排除。
- ViT 小模型：ViT 论文（arXiv:2010.11929）只在 ImageNet/JFT 报告数值，无 CIFAR-10 官方数值；小 ViT 从零训 CIFAR-10 需数百 epoch 加强增广才可比，25 分钟内不可收敛到可对比水平，排除。
- FashionMNIST：官方源为 AWS 欧洲 S3（fashion-mnist.s3-website.eu-central-1），国内不稳；论文（Xiao et al. 2017）基线数值记忆不可靠，无可靠官方数值，暂排除，[verify] 后轮可补。

## 可执行变更

1. 云端实测清单（执行阶段第一步，全部 HEAD/抓取，不训练）：
   - HEAD 以上全部数据直链并按结果落定"主源+兜底"两栏：cs.toronto.edu CIFAR 包、hf-mirror cifar10、ModelScope 检索的 CIFAR 数据集、ultralytics.com/assets/coco128.zip、ossci-datasets.s3.amazonaws.com/mnist、GitHub releases 的 yolov5s.pt。
   - 抓取留存：He 2016 Table 6 数值、yolov5 官方 README 预训练表与 Train Custom Data 教程页、pytorch-cifar-models README 准确率表、pytorch/examples/mnist README（99% 声明）。
   - 复核 chenyaofo 仓库训练脚本路径与入口名；确认 chenyaofo 模型库数值与论文误差率的对应关系（同 arch 同数据，用于把 README 数值并列入对比表）。
2. 软件侧待办联动（与验收同批）：a) 数据集自动获取规范落地（按本次三份数据集 URL 矩阵实现"官方直链失败自动切镜像整包"逻辑）；b) 入口识别补 main.py 分支并保证不误判为推理脚本；c) 指标解析补 stdout "Accuracy ... : XX %" 模式，与 results.csv 解析并列；d) verify 容错：coco128 与 yolov5s.pt 下载失败时输出明确回退动作而非中断。
3. 验收执行编排：三机并行，每机两阶段（阶段一：全链路到"训练真实产出指标"的冒烟，约 5-10 分钟；阶段二：全量配置跑到论文级数值）。机1 与机3 先跑（可验证依赖自举与数据获取），机2 在软件数据规范落地后跑，用以回归验证该改进。
4. 指标对比报告字段口径（写入报告模板）：数据集、规模（样本数/epoch/bs/分辨率）、训练总时长、复现数值、论文或官方数值、数值出处（论文表号或 README 位置）、同量级判定（等值对比或口径说明）、截断差异原因。三机输出统一为同一模板，机2 必须单列 COCO 全量口径行。

## 主要不确定点（对结论影响小、由执行期兜底）
- 全部镜像类 URL 与 s3/官方站国内可达性未经真机 HEAD，已全部标 [verify] 并给出每条的回退链。
- chenyaofo 仓库训练脚本与模型库数值页、yolov5 官方教程历史数值页需抓取复核后才能作为"原文出处"打印进报告。
- 落选池中 FashionMNIST 与 DCGAN 仅当执行轮出现富余预算或需要更多边界场景时才启用，不阻塞当前三机验收。
