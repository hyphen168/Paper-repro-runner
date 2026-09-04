# 专家组·端到端流程设计（d_flow）：无数据集时的决策与执行流规范

> 适用范围：auto_run=true（auto/tune）或 run 模式且 auto_download_dataset=True 时的 dataset 步骤。
> 事实基线（已复核源码）：DatasetDiscovery.build_remote_script/build_remote_command/extract_payload（载荷 PAPER_REPRO_DATASET_JSON=，env 文件 .paper_repro_dataset.env）；remote_runner 的 degrade 分支与标记 [paper-repro-degrade]/[paper-repro-degrade-fatal]；app.py 高级选项 data_config 输入与 split_enable。本文件只定决策/执行/日志/UI 规范；候选源直链与可达性以 a_sources/b_download 校验版为准，边界约束见 e_safety/c_audit，冲突以 lead_spec 为准。

## 决策

### 1. 数据集资源优先级决策树（终版）

```
训练相关模式下的 dataset 步骤，资源优先级：
P0 用户显式输入（data_config 非空：仓库内 YAML 相对路径 / ZIP·TAR 直链，支持多候选逐级择优）
   └─ 全部候选失败 → P0 级失败，不落入自动发现
P1 仓库自带可用配置（目录名身份词命中且 train/val 已就绪）→ 直接使用，零下载
P2 仓库配置缺数据但 YAML 声明官方 download → 按声明执行（多源回退 + 体积/磁盘护栏）
P3 仓库无匹配配置 → README 链接抽取（dataset|data|.zip|.tar，沿用现有正则）→ HEAD 探测排序后择优
P4 自动候选源：任务族推断 → 该族默认候选集（国内可达优先排序）→ 逐源 HEAD 探测 → 择优下载
P5 明确降级（唯一非训练出口，仅 auto_run 且无 run_command 时）；run 模式同位置报错退出（保留 degrade-fatal 语义）
```

每级失败先落日志、再按级给最终消息模板（统一前缀 `[数据集]`，中文、无 emoji）：

- P0 失败日志：`[数据集] 失败 级别=P0 原因={NETWORK_UNREACHABLE|ARCHIVE_INVALID|HTTP_{code}}`；消息模板：`您填写的 N 个数据地址均不可用（已尝试：{前3个}）。请确认地址公开可下载、无需登录、且为 zip/tar 包；或改填仓库内 YAML 相对路径后重试。`
- P1/P2 失败日志：`[数据集] 失败 级别=P2 配置={yaml} 官方下载未完成：{stderr 前三行}`；消息模板：`仓库 YAML 声明的下载源不可用。请把该数据集的国内镜像直链填入"数据集"输入框（支持逗号分隔多候选，自动择优），系统将跳过自动发现直接使用。`
- P3 失败日志：`[数据集] 失败 级别=P3 README 候选 N 条全部 HEAD 失败（{前3域名}）`；消息模板：`仓库内无可用数据配置。已按任务族推断为 {family}，将尝试自动候选源；您也可手动填写直链跳过此步。`
- P4 失败日志：`[数据集] 失败 级别=P4 自动候选源 M 个均不可达或体积超限（{域名列表}）`；消息模板：`候选源全部不可用（已尝试 M 个）。若判定为网络限制，请改用"自定义命令"模式并填写国内镜像下载命令，或换一台网络更宽松的实例。`
- P5 降级（auto 且无 run_command，保留 [paper-repro-degrade] 标记与既有文案，其后追加）：`[数据集] 降级 原因码={reason_code} 已按安全检查收尾，未执行训练。下一步：① 在高级选项"数据集"粘贴直链（多候选自动择优）；② 从候选默认集（见 §2）选一个填入；③ 改"自定义命令"手写下载+训练。`
- run 模式失败（保留 [paper-repro-degrade-fatal] 与退出码 1）：`[数据集] 失败 本次为实际训练需要数据集，未执行训练，任务终止。原因码={reason_code}。下一步：填入直链或改用任务族默认集后重新提交。`

原因码枚举（写入 dataset 对象，供监控页分类渲染）：NETWORK_UNREACHABLE / DISK_INSUFFICIENT / ARCHIVE_INVALID / NO_CANDIDATE / SCRIPT_FAILED / AMBIGUOUS_REPO / USER_INPUT_FAILED。

### 2. 任务族推断与"最合适地址"映射

推断信号（按强度加权，任一强信号即可定族，弱信号需 ≥2 处一致）：① run_command 关键词（detect/segment/gan/train 的 cls/…）；② 入口脚本名与 import（yolo/mmdet/ultralytics→det；mmseg/unet/segmentation→seg；dcgan/cyclegan/pix2pix→gan；torchvision 分类头→cls；transformers/bert/gpt→nlp）；③ README 标题与关键词；④ 仓库目录名身份词（复用现有 identity 拆词机制）。产出（family, 置信度 0-1）。

各族默认候选映射（"体积适中、单卡 RTX4090 训练时间可接受、国内可达"为选型判据；URL 与校验值以 a_sources 校验版为准，此处给优先级）：

| 族 | 默认候选集（按优先级） | 体积/时长档位 |
|---|---|---|
| det | COCO128（YOLO 形态，images/ 与 labels/ 同级）→ 工业身份词命中（neu/crack/defect）时 NEU-DET 类集 → VOC 子集 | 约 7MB/分钟级；超 2GB 不自动选 |
| seg | VOC-seg 或 CamVid 类小集（≤1GB） | 训练分钟级 |
| gan | CIFAR-10（约 160MB 包）→ 人脸类仅当命中 celeb/anime/face 且有国内镜像 | 约 30-60 分钟 |
| cls | CIFAR-10 / FashionMNIST（取小者） | 分钟级 |
| nlp | wikitext-2 / SST-2 类（<50MB），且仅当证据强度足够 | 分钟级 |

保守策略：置信度 <0.6 或族重叠（如 det∩seg 同时命中）→ 不自动下载，输出 AMBIGUOUS_REPO，列出命中族与其最小默认集供用户一行直链选择；任何候选预估下载 >2GB、需登录、或磁盘余量 <1.5GB（沿用现有硬下限）→ 拒绝并走 P5 指引，宁降级不误下大文件（延续"20GB Argoverse 误下"教训）。

### 3. 状态与监控（dataset 步骤日志规范）

阶段行统一前缀 `[数据集]`，逐行实时回流（复用现有 on_step 每 0.2s 轮询通道，不新增连接）：

```
[数据集] 发现中 来源={user_input|repo_yaml|readme|auto_catalog}
[数据集] 候选 N 个（列前 3 源域）
[数据集] HEAD 探测 M/N 可达（跳过原因：超时/超体积上限/需登录）
[数据集] 下载中 已用 Xs 已下载 A MB / 总量 B MB（每 30s 或每 5% 一行；拒 HEAD 时按累计字节估算）
[数据集] 解压中 → 校验 train/val 文件数与结构
[数据集] 划分 train/val/test（启用 split 时，软链接）
[数据集] 就绪 YAML={相对或绝对路径} env=已写出
```

失败不静默 degrade：degrade 分支打印原文案后必须追加一行可操作指引（§1 P5 模板）；dataset 对象仅追加字段 reason_code、candidates_tried（前 3）、suggested_actions（两条）、disk_free_gb，既有 degraded/reason 字段与载荷结构不变，历史任务渲染不回归。兼容性护栏：保留 [paper-repro-degrade] 标记（execute() 靠它识别降级）、保留 PAPER_REPRO_DATASET_JSON= 载荷与 .paper_repro_dataset.env 写出、步骤顺序不变。

## 可执行变更

### 4. 与 UI 配合（app.py 高级选项 + 结果卡）

- data_config 帮助文案重写为："留空=系统自动发现。可填：① 云端仓库内 YAML 相对路径（如 data/coco128.yaml）；② ZIP/TAR 数据包直链——自动下载解压并生成 YOLO 形态配置（images/ 与 labels/ 同级，无 val 时自动复用 train）；③ 多候选一次粘贴：用逗号或换行分隔，按顺序 HEAD 探测并自动择优。云端会自动补试 hf-mirror/ModelScope/OpenDataLab 等国内可达镜像。"（无 emoji，不新增依赖。）
- 提交前本地探测提示：data_config 含 http(s) 时，本机先并行 HEAD（5s 超时，跳过需登录与预估 >3GB 者），以 caption 展示各候选可达性与预估体积；本地探测仅提示不阻断（本机与云端网络不同），云端仍走多源回退。
- 结果卡 dataset 渲染：degraded 时展示原因码 + 建议动作两行，并提供"复制推荐直链"操作；无新字段时沿用旧文案。

### 5. 回滚与清理

- 半截下载隔离：下载一律写 `.part` 临时文件（如 `datasets/.tmp_xxx.zip.part`），校验完整后才 rename 为正式名，杜绝半包被 is_zipfile 误判；解压先进 `.unpacking_<name>/`，校验 train/val 齐备后整体改名。
- 落盘与磁盘汇报：默认沿用 repo/datasets（兼容 .paper_repro_dataset.env 相对路径语义与既有测试）；检测到系统盘余量 <2GB 时切换到 /root/autodl-tmp/datasets 并在 YAML 写绝对路径（开关 PAPER_REPRO_DATA_HOME 控制）。步骤开始先清 24h 前的 *.part 与 .unpacking_*；成功或降级收尾均输出 `[数据集] 磁盘占用 datasets=X GB 可用=Y GB`，下载前如超限先报余量与候选体积，不静默占满 30G 系统盘。
- 回归护栏：改动仅追加文案/字段/阶段行；远端仅用 Python 标准库（urllib/zipfile/tarfile/shutil），wget/curl/aria2 仅可选探测；pytest 88 全绿与 AppTest 0 异常不受影响。

### 结论

按 P0 用户输入 → P1 仓库自带 → P2 YAML 官方下载 → P3 README 链接 → P4 任务族推断的国内可达默认集 → P5 明确降级带指引的决策树落地 dataset 步骤，配合阶段化日志、多候选 UI 与 .part 回滚清理，即可在无数据集时让训练类任务逐级自救，且只降级、不静默、不占满磁盘，全部变更向后兼容。
