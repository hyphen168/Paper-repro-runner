# Research: AutoDL/中国大陆网络下公开数据集候选源清单与择优技术（a_sources）

## Summary
经复核代码基线（`dataset_discovery.py` 的 `build_remote_script` 已支持 YAML 相对路径、http(s) ZIP/TAR 直链下载解压、仓库 YAML `download:` 声明执行与磁盘 1.5GB/80% 双重守卫；空 `data_config` 时只扫描仓库内 YAML，找不到即 degraded），结论：数据源短板不在"下载执行"，而在"候选源清单与择优"缺失。方案：内置"数据集家族→国内可达镜像候选"注册表 + 云端运行时 HEAD/Range 探测择优 + README/YAML 链接抽取，用户显式 URL 永远第一优先。本会话无联网工具，矩阵 URL 均为权威稳定引用，最终以云端探测结果为准（机制见 §决策-2）。

## 决策

### 1. 代码事实基线（已文件复核）
1. **现状**：`build_remote_script` 生成自包含远端脚本（仅标准库+PyYAML），单参数 `data_config`。http(s) 直链→下载到 `root/datasets/`→解压→按 `train&val` 键的 YAML 或 `images/{train,val}+labels` 结构自动生成 YAML（无 val 时复用 train，`nc` 由 labels txt 首列最大值推断）；YAML 路径→校验完整性→缺失且带 `download:` 时执行（http 包走重定向/重试下载，Python 片段或 shell 命令按原样执行）。空串→按"仓库目录名拆词身份匹配"扫描本地 YAML，多候选歧义即报错拒绝，README 链接只作提示不下载。`extract_payload` 从 `PAPER_REPRO_DATASET_JSON=` 反向还原。UI（app.py 高级折叠区）已有 `data_config` 直链输入、划分比例、`auto_download_dataset=True`。[Source: 本机 dataset_discovery.py / app.py 复核]
2. **结论**：自动发现只覆盖"仓库自带数据包"，没有覆盖"仓库无数据但训练需要公开数据集"的场景——这正是 task-a51308f3 降级根因。需要新增**镜像候选注册表+择优**，而下载/解压/YAML 生成管道可原样复用。

### 2. 数据源可达性矩阵（择优候选按此构造）
规则：所有候选统一归一为**标准库 urllib 可下的 ZIP/TAR 直链或一条可执行命令**，生成时即把 HF id/镜像 id 展开成直链。

| 数据集/家族 | 官方/海外 | 国内推荐渠道 |
|---|---|---|
| COCO 2017 | http://images.cocodataset.org/zips/（train2017≈19GB、val2017≈780MB、annotations 240MB；http 明文，大陆慢/不稳） | ModelScope 搜索 COCO 镜像组；OpenDataLab `odl get COCO`（需 token，见下）；AutoDL 公共数据集若可选装 |
| PASCAL VOC2012 | http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar（≈2GB，牛津源） | OpenDataLab VOC；ModelScope/HF-mirror 镜像 |
| YOLO 小包 coco128/coco8（复现首选） | https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip（≈7MB）；其 yaml `download:` 字段同源 | 直接套用现有 ghfast.top 加速前缀变体：`https://ghfast.top/<原github直链>`（注意 codeload/objects.githubusercontent 重定向后加速不保证，需整链探测）；ultralytics 各数据集 cfg 的 `download:` 可解析 [Source: https://github.com/ultralytics/assets 、 https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/datasets/coco128.yaml] |
| CelebA（GAN 常用） | 官方 Google Drive（mmlab.ie.cuhk.edu.hk），大陆基本不可直连 | ModelScope 内搜 CelebA（AI-ModelScope 镜像组）；HF-mirror resolve 直链 |
| FFHQ | NVlabs 官方为 Google Drive 分包，不可直连 | OpenDataLab（odl get，需同意协议）；HF/ModelScope 站内搜 FFHQ |
| CIFAR-10/100 | https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz（海外慢） | torchvision 缓存或站内镜像；HF-mirror/ModelScope |
| MNIST | 官方 yann.lecun.com 不稳；torchvision 默认 ossci-datasets S3（大陆常不通） | 建议训练脚本改走镜像（详见可执行变更-6） |
| ImageNet 子集 | 官方需注册，禁自动 | tiny-imagenet 类（HF 仓库 resolve 直链）；不要尝试全量 |
| GLUE（NLP） | gluebenchmark.com 已不稳 | HF 规范仓库 `nyu-mll/glue`（按 config 取子集），经 hf-mirror.com 下载 |

**HF 通道**：`HF_ENDPOINT=https://hf-mirror.com` 对 huggingface_hub/datasets 库透明生效；更通用的是**无依赖直链** `https://hf-mirror.com/datasets/{org}/{name}/resolve/main/{path}`（官方规则同款换 host）。gated/需许可的数据集自动跳过。[Source: https://hf-mirror.com 、 https://huggingface.co/docs/hub/en/datasets-usage]
**ModelScope**：大陆阿里云 CDN，快；CLI `modelscope download --dataset {org}/{name} --local_dir <dir>`；也可用其 HTTP 文件接口，站内搜索即得 id（社区镜像常用 `AI-ModelScope/{HF名}`）。[Source: https://modelscope.cn 、 https://github.com/modelscope/modelscope]
**OpenDataLab**：`pip install opendatalab` + token（站内生成），`odl get COCO` 式拉取；优点：COCO/VOC/FFHQ 等大型视觉集全；缺点：多数需登录并同意下载协议，**headless 自动流程默认不启用**，仅当用户填入 token 环境变量时才进候选。[Source: https://opendatalab.com 、 https://github.com/opendatalab/opendatalab]
**Kaggle**：需 kaggle.json 凭据、大陆可达性一般，与"无凭据自动跑"冲突——**评估结论：v1 不内置**，仅在 UI 帮助文案提示用户可先用 `kaggle datasets download` 自行灌入云端数据盘。[Source: https://www.kaggle.com/docs/api]
**AutoDL 公共数据集/学术加速**：官方帮助文档（autodl.com/docs 站内页）说明实例可选挂公共数据集与学术资源加速；挂载点通常在数据盘，须以控制台为准。[Source: https://www.autodl.com/docs/] 运行时先探测常见挂载目录（见可执行变更-1），命中即零下载复用，网络成本最低。
**清华/阿里镜像**：对数据集无通用官方镜像；但其 pip/conda 源已在 pipeline 使用。GitHub 系加速（ghfast.top 等）属非官方无 SLA，须探测后使用。[Source: https://github.com/ghfast/top（项目页）——以实际可达为准]

### 3. 自动择优算法（决策）
**优先级（递减）**：T0 用户显式 URL/YAML（不做镜像替换，只做合法性+体积校验）＞ T1 仓库声明（YAML `download:`、README/脚本抽出的链接，须通过主题命中与安全过滤）＞ T2 注册表镜像候选（同数据集多源：官方/HF-mirror/ModelScope/OpenDataLab(仅带 token)/github 加速前缀变体）。**同层择优用探测分数**，而不是静态顺序。
**探测**：HEAD 优先（6s 超时），不支持则 `Range: bytes=0-0` GET；记录 status(200/206)、Content-Length、Content-Type、耗时；再对前 2 名做 256KB Range 测速采样得速率，预估下载时长=size/rate，取最短且 ≥200KB/s 者（小包 <50MB 免测速，直连最快者）。**预算**：单候选 ≤12s，候选 ≤6 个，探测阶段总预算 ≤45s；下载沿用现有 3 次重试/600s 单次超时，失败自动切下一候选。**安全**：仅 http(s) 与白名单命令形态；总大小 > free×80% 或 <1.5GB 拒绝（沿用现有守卫）；license 非公开(gated/需协议)一律不入候选。
**伪码**：
```
cands = tier_sort(user_url, repo_declared, registry_expand(name))
probe_budget=45; ok=[]
for c in cands[:6]:
    r=probe(c, timeout=6)          # HEAD or Range:0-0
    if r.status in (200,206) and r.size_ok():
        ok.append(c.score(r));    # size/known
if len(ok)>1 and largest.size>50MB:
    s=probe_range_speed(ok[:2], n=262144); pick=min(est_time)
else: pick=ok[0]
dl(pick) or next_ok_fallback()   # 3 retries, follow redirects
```
**结果透明**：失败/降级 reason 中带上前 3 名候选 URL（延续现有"README 中发现候选链接"的提示风格），用户可复制改进。

### 4. 链接抽取规则（决策）
- 抽取面：README*.md、`docs/`、`*.yaml/yml`、`*.sh/requirements/run*.py` 中的链接与命令；只在云端仓库内抽取（远端脚本内做，Windows 侧不重复抓）。
- 形态与正则：直链 `.zip/.tar/.tar.gz/.tgz/.tar.bz2/.7z`（7z 不支持则剔除）；`wget/curl/aria2c/gdown` 命令（含 `-O name` 时校验 name 后缀）；HF 仓库 id：`huggingface.co/datasets/{org}/{name}` 与 `HF://datasets/...` → 展开 hf-mirror resolve 直链；Kaggle id：`kaggle.com/datasets/{owner}/{name}` → 仅登记不下载（v1）；yaml `download:` 字符串（http 或代码/命令，现状已支持）。[Source: 代码复核 + https://huggingface.co/docs/hub/en/datasets-usage]
- 过滤：去重、去 .git 路径、URL 含 `?token=`/`key=` 等敏感参数直接丢弃、非白名单命令丢弃、gdown/google drive 直链丢弃（无法 headless）、候选 ≤10 个且仅保留扩展名/关键词（dataset|data|coco|voc|celeba|ffhq|cifar|glue|mnist）命中者。危险模式：陌生仓库的 `download:` 是 shell 脚本——现状设计为"仅当 YAML 已被身份词命中后才执行"，需保持该闸门并把执行结果 stderr 摘要写回日志。

### 5. 许可与体积提醒（决策）
- 体积：HEAD Content-Length 缺失即视为大包；>2GB 在任务日志醒目提示"预计 X GB、来源 Y、将写入数据盘"，不阻断（AutoDL 数据盘常态充足），系统盘(<30G)场景自动把 `root/datasets` 改指数据盘（见变更-2）。
- 许可：注册表内每条候选可附 license 字段，落盘到 payload 元数据仅供 UI 展示；**不自动点击同意任何 license/协议**（gated 即排除）；OpenDataLab/Kaggle token 只允许来自用户填的环境变量，禁止出现在 URL/表单值中（敏感零存储）。

## 可执行变更
1. **本地挂载/缓存优先探测**：dataset 脚本进入下载前，先探测 AutoDL 公共数据集常见路径（数据盘根、`/root/autodl-tmp/public-datasets`、仓库内 `datasets/data`），找到含 COCO/VOC 等目标结构的目录即直接生成 YAML、标记 `downloaded:false,source:local_mount`。零网络成本，应放在 T1 之前。
2. **数据家目录环境变量化**：`build_remote_script` 的 `root/'datasets'` 改为读 `PAPER_REPRO_DATA_HOME`（默认不变），任务创建时若检测仓库位于系统盘且包 >2GB，自动 export 到数据盘。改动小、pytest 兼容（默认行为不变）。
3. **注册表常量模块**：新增 `dataset_registry.py`（Windows 侧本地纯数据，无新依赖）：`{name_token: [Candidate(label, url_or_expander, size_hint_gb, license, tier)]}`，含官方/镜像/加速前缀变体展开函数与 HF resolve 换 host 规则；配套 `tests/` 单测（保持 pytest 88 全绿并增加新用例数）。
4. **候选下发通道**：`build_remote_command` 增加可选第二参数：云端先写 `.dep_dataset_candidates.json`，再以第二 argv 传入（旧调用无参时行为不变，向后兼容）；脚本对注册表候选执行 §决策-3 探测择优，并对 README 抽取链接做安全过滤后并入 T1。
5. **降级 reason 可操作化**：找不到可用源时，reason 追加"可尝试：<前3候选 URL>；或在提交表单'数据集'栏粘贴直链"，直接呼应本任务用户诉求（"用我提供的 url 或者自动寻找"）。
6. **MNIST/ImageNet 子集注意**：不改 torchvision 源码，改为检测仓库训练脚本里 ossci/lecun URL 时给出提示并建议候选镜像（属文档+日志提示，不动用户代码）；对 ImageNet 全量永远不自动下载。
7. **UI 微文案**（中文、无 emoji，AppTest 0 异常约束下只动 help/caption 文本）：`data_config` help 增加"支持国内镜像直链（hf-mirror/ModelScope/OpenDataLab 等）与 ghfast.top 加速前缀，系统自动测速择优"；不改控件结构。

## Sources
- Kept：
  - https://github.com/ultralytics/assets 与 https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/datasets/coco128.yaml — coco128 官方小包与 yaml download 字段，复现首选数据。
  - https://hf-mirror.com（含 hfd 用法）与 https://huggingface.co/docs/hub/en/datasets-usage — HF 镜像环境变量与 resolve 直链规则。
  - https://modelscope.cn 、 https://github.com/modelscope/modelscope — 大陆阿里云数据集/模型源，CLI download。
  - https://opendatalab.com 、 https://github.com/opendatalab/opendatalab — 大型视觉集（COCO/VOC/FFHQ 等），需 token。
  - https://www.kaggle.com/docs/api — 凭据要求佐证"v1 不内置"决策。
  - https://www.autodl.com/docs/ — AutoDL 公共数据集/学术加速官方入口。
  - http://images.cocodataset.org/zips/ 、 http://host.robots.ox.ac.uk/pascal/VOC/voc2012/ 、 https://www.cs.toronto.edu/~kriz/cifar.html 、 https://mmlab.ie.cuhk.edu.hk/projects/CelebA.html 、 https://github.com/NVlabs/ffhq-dataset 、 https://huggingface.co/datasets/nyu-mll/glue — 官方直链基线。
  - 本机 dataset_discovery.py / app.py / repo_crawler.py — 代码事实基线复核。
- Dropped：本会话未获得任何可用的第三方转述类搜索源（无联网工具），故不收录 SEO/转述页，全部以上述一手引用为准，真实可达性交由云端运行时探测裁决。

## Gaps
- 本会话无 web_search/fetch 工具，无法实测各镜像 2026 年现网可达性与测速；矩阵中标注"站内搜/以实测为准"的仓库 id 需在下次运行任务中用 HEAD 探测批量验证一次，把结果回填注册表。
- AutoDL 公共数据集的确切挂载路径与数据集清单以控制台/官方帮助页为准（本简报未实证）。
- repo_crawler.py 的 AutoRepoDatasetCrawler 仅用于候选仓库搜索（requests+bs4，Windows 侧），未与数据集注册表打通——是否复用之由后续技术方案评审。

## Supervisor coordination
本子任务未阻塞、无决策依赖；无需协调。已按运行路径写入 a_sources.md。
