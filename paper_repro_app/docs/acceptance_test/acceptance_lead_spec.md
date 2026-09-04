# 三机真机验收与普适性测试实施方案 v1.0（专家组主导裁决版）

四份报告（a 选文 / b 链路 / c 普适审计 / d 指标口径）已通读。裁决要点：DCGAN 无官方数值落选（b/d 与 a 一致）；裸软件仅 yolov5 可零补丁直跑（b 实测判定），ResNet 与 MNIST 路径各需三处小补丁；c 的"论文指标无注入入口"与 d 的"对比表伪造占位行"合并为 P0-1；数据集多候选规范本轮不落地（数据可控、避免回归），只修两处致命缺陷（G2a/G2b）。本方案为执行唯一依据。

## 一、总纲

目标：三台全新 4090D 真机并行跑通三篇真实论文的完整复现流水线（自举环境、真实训练、全指标收集），产出带出处与口径的"论文值 vs 复现值"对比与总报告；同时按"陌生人拿到 zip 即用"标准完成普适性 P0 修复并复核开箱路径。

原则：
1. 诚实对比：无官方数值不入选；L1/L2/L3 分级强制标注，禁止把冒烟包装成复现（d 规范直接引用）。
2. 最小补丁：只落 G1+G2a+G2b+G3 与 P0-1/P0-2 等必改项；全量数据集多候选、UI 向导、防火墙改造等一律后置。
3. 三机即三重复：同型机天然构成种子 0/1/2 的重复样本，L1 篇目按此取均值汇报（d 第 3 节）。
4. 凭据纪律：三机密码仅测试内存使用，文档/日志/报告零明文（脱敏已接入 sanitize，验收时复查）。
5. 可回放证据：复现命令全文（trace 已具备）、训练日志尾行、指标摘要行、权重产物路径，随报告归档。

验收判据一句话：三机各至少一条任务 status=success 且确有训练输出；L1（ResNet-20 CIFAR-10）复现误差与论文差 ≤3pp；L3 篇目结构判据通过（loss 单调降、无 NaN、吞吐与官方同量级）；普适性 P0 清单全部落实并可复核。

## 二、三篇选文终案

| 篇 | 机器 | 论文与仓库 | 任务族 | 数据源与规模 | 预期指标区间与口径 | 定级 | 风险 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 篇一 | 机1 | ResNet（He et al. 2016, Deep Residual Learning, CVPR）；仓库 chenyaofo/pytorch-cifar-models（与论文同构窄体 ResNet-20，0.27M 参数）；备选 kuangliu/pytorch-cifar | 图像分类 | CIFAR-10 官方 tar 162.6MB，主源 https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz（verify-on-cloud），兜底 hf-mirror/ModelScope 同包；训练集 50k | 论文数值：8.75% 误差（He 2016 论文 Table 2，20-layer，v1 原值；同表 56-layer 6.97% 仅参考）。200 epoch 预估 15-25 分钟（含自举）；acc 约 91.5-92%（err 8.0-8.5%）。达标判据：err−8.75 ≤3pp 且末 20% 轮次改善 <0.1pp/轮 | L1 | 训练时长压预算边缘；toronto 源国内可达性待 HEAD；镜像包校验（md5 对齐官方页面）；仓库无 requirements（G1 路径） |
| 篇二 | 机2 | YOLOv5（Jocher et al., ultralytics/yolov5） | 目标检测 | coco128 演示集 zip 约 7MB，GitHub release 直链（verify-on-cloud；仓库 data/coco128.yaml 即指该源）；训练图 128 张 | 全量口径：官方 README（tag 记录）COCO val mAP@.5:.95=37.2 仅作背景；本机对比基线用官方 tutorial 同配置 3-epoch coco128 数值 mAP@.5≈0.287（verify-on-cloud 抓 README/tutorial 留存出处）。预期本机 0.25-0.40（batch/seed 波动）。达标判据：L3 结构通过 + loss 首→末降 ≥30% | L3 | yolov5s.pt 权重可达性（不可达切 --weights "" 从零训并记录）；yolov5 数值随 tag 漂移（执行期固定 tag 记 commit） |
| 篇三 | 机3 | MNIST CNN（pytorch/examples 官方 mnist；论文背景 LeCun et al. 1998，Gradient-Based Learning, 表值 0.95% 测试误差） | 图像分类 | MNIST 自动下载约 11MB（源 yann.lecun.com / pytorch 默认，verify-on-cloud，慢则预置环境变量源）；60k 训练 | 官方 README 数值约 99%（来源：仓库 README 当前 commit）。LeCun 0.95% 为原 LeNet-5 配置，本实现（pytorch/examples CNN）非同构，仅作背景注记。达标判据：L3 结构通过 + test acc≥99%（README 值 ±0.5pp 内）；14 epoch 2-5 分钟，余量执行重运行边界（c 的密码缺失提示场景演练） | L3 | 与论文非同构，禁止宣称复现 LeCun 指标；torch 环境需自举（无 requirements 缺 torch 分支验证点——实际上该仓库带 requirements，可顺带覆盖 G1 判定逻辑回归） |

落选说明（裁决采纳）：DCGAN（Radford 2016）无逐项官方数值，违反硬约束 5，剔除；ViT/FashionMNIST 同类无官方表值或源在欧洲不可控，剔除。三篇覆盖 分类(L1/L3)+检测(L3) 两族与 文件级+stdout 两类指标形态，足以支撑验收目标；d 的"至少含一篇 L2"在无合适官方全量可收敛 L2 候选（全量需 1-8 小时类）时放宽为"L1 达标为唯一硬判据 + L3 结构判据补齐"，并自动启用 d 的降级条款：任何报告不得写"指标与论文一致"字样，统一写"L1 达标/L3 冒烟"级别。

## 三、逐篇执行清单

### 前置补丁（全局，一提交落地）
- G1（torch 自动补装）：无 requirements 仓库且 AST 依赖扫描命中 heavy=torch/torchvision 且 import 不可用时，自动按现有双源逻辑安装（cu128→cpu，复用 install_req_file 内 torch 段写法）。文件：remote_runner.py（dependency 步骤命令串 heavy_hit 分支）。影响：篇一（chenyaofo 无 requirements）。
- G2a（py3.10 tar 崩溃修复）：dataset_discovery.py 中两处 `extractall(filter=...)` 改为逐成员安全提取 helper（跳过 ../、绝对路径；目录先行）。影响：篇一 CIFAR tar 直链当前必崩。
- G2b（非 YOLO 结构兜底）：dataset URL 直链分支解压后无 images/ 与 labels/ 时，写 `PAPER_REPRO_DATA_CONFIG=<解压根父目录>` 到 env 文件并 exit 0（供自定义 run 命令以 --dataroot/--data-dir 消费），不再 SystemExit。影响：篇一 CIFAR（--data-dir 场景）与未来任意 raw 数据集。
- G3（stdout 指标兜底）：.collect_results.py 追加白名单正则与四道校验（时间线/单位域/sanity/冲突取后值）：accuracy=`Accuracy of the network on the 10000 test images:\s*([\d.]+)\s*%`；Loss_D/Loss_G=`Loss_D:\s*([\d.eE+-]+)\s+Loss_G:\s*([\d.eE+-]+)`；吞吐与 epoch_time 一组；acc/mAP 域 [0,100]，loss 必须为正；全无命中时 verdict=no_metrics 且 run 后无 epoch 推进判"训练未发生"走失败分支。文件：remote_runner.py collect 段内嵌脚本 + storage_utils.py 落库 payload 扩展 verdict。
- P0-1（对比表去伪 + 论文基准）：comparison_table.py 删除 N/A 占位默认行（现状会在无数据时伪造 Top-1/mAP/F1 行，d 判为最大误导源）；新增 docs 或包内 paper_claims.json（三篇录入：metric/paper_value/unit/source 表号或 README commit/direction/level/caliber{dataset,epochs,batch,seed}）；storage_utils 组装表前非空与 direction 校验；未录入基准时整表替换为一行"论文基准未录入，本次未做指标对比"。文件：comparison_table.py、storage_utils.py、新增 paper_claims.json。
- P0-2（密码机恢复提示）：监控页"重新执行流水线"在任务无内存密码时先要求现场输入（st.text_input type=password + 提交），并提示后台线程为窗口生命周期级、勿关闭控制台。文件：app.py 监控区。
- P0-3 附带小修：使用说明 txt 纳入 zip 顶层（make_dist.py）；README/pyproject Python 版本口径统一 3.11+。

### 篇一执行（机1，ResNet-20 CIFAR-10，L1）
1. 云端 HEAD：toronto CIFAR 直链与镜像；md5 与官方页对齐（verify-on-cloud 结果写入执行记录）。
2. 提交（run 模式，自定义命令，规避入口识别 miss——ModelDiscovery 扩展列为不做项）：
   `python main.py --model resnet20 --epochs 200 --seed 0`（实际参数以仓库 README 实测为准，落 execution log）。
   data_config 填 CIFAR tar 直链（G2a/G2b 生效：解压 → env 指向根目录 → --data-dir ${PAPER_REPRO_DATA_CONFIG} 变体按仓库实际参数修正）。
3. 预期：conda 自举+torch（cu128）+训练 200 epoch，15-25 分钟；产出 acc per-epoch stdout → G3 提取 acc；末值折算误差。
4. 判据：err−8.75pp ≤3pp 且收敛；通过则记 L1 达标（单种子 0；因接近预算不做三种子）。

### 篇二执行（机2，YOLOv5s coco128，L3）
1. HEAD：coco128 release zip 与 yolov5s.pt；README/tutorial 数值出处抓取留存（记 tag/commit）。
2. 提交（auto 或 run）：data_config=coco128 zip 直链（引擎自动下载解压+自动 YAML）；`python train.py --data ${PAPER_REPRO_DATA_CONFIG} --epochs 3 --img 640 --batch 16 --weights yolov5s.pt（不可达则 ''）--seed 0`。
3. 预期 8-15 分钟；results.csv 由 collect 现有规则覆盖（6/9 项），G3 兜底余项。
4. 判据：L3 结构通过（loss 降≥30%、无 NaN、产物 best.pt 存在）+ 输出 mAP@.5 与官方 tutorial 值并列（注明非同一数据规模外推不可比）。

### 篇三执行（机3，MNIST CNN，L3 + 边界演练）
1. HEAD：mnist 源可达性（yann.lecun.com 或镜像）。
2. 提交（run 模式）：`python main.py --epochs 14`（requirements 路径验证 + G1 逻辑回归确认不误触发）。
3. 预期 3-6 分钟；test acc stdout → G3 提取。
4. 边界演练（时间余量内）：完成后点击"重新执行"，验证 P0-2 密码现场输入提示出现且补密后可重启（无密码时给可操作报错而非静默失败）。

### 每篇附加
- collect 结束后 artifacts 回传本地 checkpoints/{task_id}/（d 第 6 项最小版：best.pt/last.pt 拉回并登记 manifest；若时间不足则登记远程路径）。
- 结果落库后，由执行脚本汇总生成对比表与 markdown 报告到 docs/acceptance_test/results/篇名/。

## 四、数据集获取落地取舍

裁决：本轮**不落地多候选自动寻源规范**（dataset_lead_spec 全套），只修两处致命缺陷（G2a py3.10 崩溃、G2b 非 YOLO 结构兜底）并沿用既有用户 URL 直链能力。
理由：1) 本次三篇数据源单一可控（直链或仓库自动下载），多候选择优属增强而非阻断；2) 大改引入回归会污染"验收"判定（b 已警告先修 G2a/G2b 否则篇一在 dataset 步骤 fatal）；3) 数据规范全套（源矩阵/测速/择优）在三机验收通过后作为独立下一轮落地，验收数据反哺其候选源优先级。降级文案（degrade reason_code）随 G2b 顺带补一行可操作指引，不单独铺开。

## 五、普适性 P0 修复清单（c 收敛，含裁决取舍）

1. 论文指标注入闭环（=P0-1）：paper_claims.json + 对比表去占位 + 报告渲染口径节。文件：comparison_table.py / storage_utils.py / 新增 paper_claims.json。
2. 密码机恢复链路（=P0-2）：重执行缺密码现场输入提示。文件：app.py。
3. 数据集真机闭环预检（执行纪律，非代码）：三篇数据源全部先 HEAD/下载实测通过才提交（含 md5/解压冒烟），auto 模式 degrade 打断 30 分钟级任务的根因从选材上排除。文件：无（执行 checklist）。
4. 指标可收集性（=G3）：stdout 正则兜底 + 四道校验 + verdict，避免"指标都要"落空。文件：remote_runner.py / storage_utils.py。
5. 附带：使用说明入 zip 顶层（make_dist.py）；Python 版本口径统一 3.11+（README/pyproject）。
6. 附带：app.py 底部遗留 main() 死代码删除（c 指出再启 8503 实例的风险）。

不纳入 P0（明确后置）：AutoDL 三步引导折叠与表单高亮样例（B 级体验，P1）；0.0.0.0→127.0.0.1 默认+LAN 开关（P1）；启动器端口就绪后再开浏览器（P1）；杀软/MOTW 文案（P1）；示例任务种子（P2）；verify 容错与 L1/L2 多主机收尾（P1，已部分在库）；nohup/daemon 断链保护（P1，执行期间以界面警示"勿关控制台"替代并承担残留风险）；ModelDiscovery 入口扩展（P2）。

## 六、指标对比口径与报告模板（d 收敛）

- 分级：篇一 L1、篇二 L3、篇三 L3；报告标题与结论一律带级别徽章（L1 达标 / L3 冒烟），禁用"与论文一致"表述。
- 表列（沿用五列 + 口径列）：指标 | 论文值[出处] | 本机复现值 | 差距（pp 绝对值 + 相对参考） | 口径说明。
- 出处格式：论文 Table 2（He 2016，20-layer 8.75% err）／仓库 README（commit hash）／官方 benchmark；无出处不填行。
- 差距方向统一"复现−论文"，越低越好指标（err/loss）翻符号；主判据 pp。
- 报告结构（report_generator 渲染节点）：基本信息 → 级别结论行 → 对比表 → 口径说明（epochs K/Y、seed、batch 单卡归一、val 划分、单次/均值）→ 证据三件套（日志尾 30 行、[指标结果] 摘要、复现命令全文 trace、权重产物路径）→ 风险与结论。篇一附带三机同型说明（本次单机单种子，落入论文报告口径带内即视为一致）。
- 阈值常量：分类 top-1/err ≤3pp；loss 仅趋势；L3 结构判据 loss 降≥30%/无 NaN/吞吐同量级 ±50%。首批实测后若同配置多 seed 方差 >0.8pp 则阈值放宽至均值±2 倍 std 带（d 校准条款）。

## 七、执行顺序与验收门

执行顺序：
1. Phase 0 补丁：G1+G2a+G2b+G3+P0-1+P0-2+P0-3 一提交；pytest 全绿（现 88 基线）、bash -n 远端脚本校验、AppTest 0 异常。
2. Phase 1 云端源实测：三数据源/权重 README 出处 HEAD 抓取（半小时内完成，结果落 execution log，任何 verify-on-cloud 失败即换兜底源并在记录中标注）。
3. Phase 2 三机并行：同一应用 DB 以 storage API 提交三任务（对应机 1/2/3），各自后台执行；每 2 分钟轮询状态；任一篇 failed 即冻结该机定位（问题清晰直接修复重跑，复杂或跨模块则成立专项组）。
4. Phase 3 汇总：G3 verdict + paper_claims 组装三张对比表与三份报告；总报告（docs/acceptance_test/results/SUMMARY.md）含普适性 P0 复核清单勾选。
5. Phase 4 评估与收尾：判据打分；清理测试任务记录标记（保留日志）；git 提交（不含密码与临时脚本）。

验收门：
- 篇一通过 = status
验收门：
- 篇一通过 = status success + 确有 200 epoch 训练输出 + err 与 8.75 绝对差 ≤3pp 且末 20% 轮次收敛（改善 <0.1pp/轮）+ 证据三件套齐；未收敛或超时（≥40 分钟）判不通过，降级改 100-epoch 档重跑并改标 L2 外推。
- 篇二通过 = status success + loss 首末降 ≥30% + 无 NaN + best.pt 产物存在 + mAP@.5 与官方 tutorial 值并列展示（不等比宣称）。
- 篇三通过 = status success + test acc ≥99% 且 ≥ README 值−0.5pp + P0-2 重执行密码提示演练符合预期。
- 普适性门 = P0 六项全部落实 + 由 make_dist 新 zip 解压副本执行安装-启动 AppTest 冒烟 0 异常 + 使用说明位于包内顶层。
- 汇总门 = 三篇报告与总报告齐 + 全文无密码明文 + git 记录干净（不含临时脚本与凭据）。

不做清单（明示）：不跑 ImageNet/COCO 全量与任何 8 小时级训练；不落地数据集多候选自动寻优（作为验收后下一轮，以验收数据反哺候选源优先级）；不做 UI AutoDL 向导、演示种子、LAN 开关与 nohup 断链保护（P1/P2）；不改动天气/昼夜/手动城市等视觉子系统；不引入新框架与图标字体；不把 L3 冒烟结果写入任何"与论文一致"表述。

参考出处（执行期抓取留存，均标 known 或 verify-on-cloud）：He et al. 2016 arXiv:1512.03385 Table 2（20-layer 8.75% error）；chenyaofo/pytorch-cifar-models README（resnet20 精度行）；ultralytics/yolov5 README Models 表与官方 Tutorial coco128 3-epoch 段；pytorch/examples/mnist README；LeCun 1998 论文（0.95% error，背景注记，不作对比宣称）。
