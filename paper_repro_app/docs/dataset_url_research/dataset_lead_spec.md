# 数据集自动获取与 URL 直链增强规范（主导裁决版 v1.0）

五份报告（a 源调研 / b 下载引擎 / c 审计 / d 流程 / e 安全）已通读；关键代码事实已在本仓库复核（含真实文件路径为嵌套包 paper_repro_app/paper_repro_app/：dataset_discovery.py 的 build_remote_script 生成自包含云端脚本、第 33 行 _URL_DL_B64 经 exec 注入 URL 直链分支（源为 _url_ds_helper.py），YAML 官方下载分支在 build_remote_script 内（约 144-146 行）也含独立解压段；remote_runner.py 443-466 dataset 步骤、962-972 降级载荷；app.py 756 data_config 输入与 779 auto_download_dataset）。分歧裁决如下，冲突以本文为准：**自动下载激进程度取 e（严格门槛）而非 a/d 的全自动族候选**；**下载引擎细则按 b 收敛为云端脚本内纯函数（不新增本地模块/依赖），由 c 确认接入点实施**；**d 的 reason_code 枚举与阶段日志作为统一字段规范**。

## 一、总纲

设计原则：
1. 用户 URL 是最高权威：填了就以它为唯一下载链（多候选逐源择优），失败即明确报错并给原因码，绝不擅自改写用户意图。
2. 自动寻源只做"高置信才动、低置信只提示"：仓库身份/代码证据不充分时，绝不替用户下载大文件（延续 Argoverse 误下教训）。
3. 下载与解压永远安全：py3.10 兼容、逐成员路径校验、压缩炸弹闸门、磁盘硬预算、失败即清理；检测与下载统一走单一函数族，不留第二份逻辑。
4. 信息可操作：失败消息带 reason_code、已尝试源、建议动作与可直接复制的候选直链；degrade 保留原标记与语义（execute 靠 [paper-repro-degrade] 识别，不回退）。
5. 向后兼容零破坏：既有载荷键、标记、自包含脚本形态、pytest 88 全绿与 AppTest 0 异常不回归。

目标观感一句话：训练任务缺数据时逐级自救——你的 URL → 仓库现成 → YAML 官方源（自动镜像回退）→ 高置信注册表样例 → 最后明明白白告诉你缺什么、下一步粘哪条链接。

## 二、数据集资源优先级与决策树终版

```
P0 用户显式输入（data_config 非空）
    形态：仓库内 YAML 相对路径（仅单条）或 http(s) 直链（单条或 [换行|分号] 分隔多候选）
    流程：逐源下载/解压/YAML 生成，首源失败自动切次源；全部失败 → P0 失败
    （auto 降级 / run fatal，消息附已尝试源与原因码），绝不回落仓库推断下载。
P1 仓库自带可用配置：目录身份词命中且 train/val 已就绪 → 零下载直接使用。
P2 仓库配置缺数据但 YAML 声明 download: → 按声明源 + 域名镜像回退下载。
P3 仓库无匹配 YAML：README 链接抽取（dataset|data|.zip|.tar）→ 仅当命中仓库身份词
    且唯一候选（score≥2 且唯一）才自动尝试；否则只提示前 3 条，不下载。
P4 任务族默认候选：score≥2 且包体 ≤100MB 才允许自动下载样例集（如 coco128≈7MB）；
    其余一律在降级消息里给出"候选清单 + 复制直链"，等用户确认。
P5 明确降级（唯一非训练出口，仅 auto_run 且无 run_command）：
    reason=原文案不变，载荷追加 reason_code/candidates_tried[≤3]/suggested_actions[2]/source_url/disk_free_gb。
    run 模式同位置报 [paper-repro-degrade-fatal] 退出（原语义保留）。
```

失败分级消息模板（统一前缀 `[数据集]`，中文无 emoji）：
- P0：`[数据集] 失败 级别=P0 原因码={code}。您提供的 N 个数据地址均不可用（已尝试前 3：{域名列表}）。请确认地址公开、无需登录、为 zip/tar 包且未超过 2GB；或改填仓库内 YAML 相对路径。`
- P2：`[数据集] 失败 级别=P2 配置={yaml}。官方下载源不可用；已自动回退镜像仍失败。建议把该数据集镜像直链填入"数据集"输入框。`
- P4 未达自动门槛：`[数据集] 提示 候选源 {前3域名}（体积 {大小}）。如需自动下载样例数据请勾选 auto 并保持默认数据集选项，或复制以下直链填入：{link}`
- P5：`[数据集] 降级 原因码={code} 已按安全检查收尾，未执行训练。下一步：①粘贴候选直链；②改"自定义命令"填写下载+训练；③若判定网络限制请换实例。`

reason_code 枚举（写入 dataset 对象供 UI 分类渲染）：`USER_INPUT_FAILED / REPO_NO_CONFIG / YAML_DOWNLOAD_FAILED / README_AMBIGUOUS / NO_CANDIDATE / DISK_INSUFFICIENT / ARCHIVE_INVALID / SCRIPT_FAILED / NETWORK_UNREACHABLE`。

## 三、候选源与择优终版（可直接写码的表）

**镜像派生函数 `_derive_mirrors(url)`（本地可单测，域名前缀替换）**：
| 原域名 | 追加候选（保持原 URL 为末位兜底） |
|---|---|
| github.com | `https://ghfast.top/{原URL}`（顺序：ghfast.top 先试，github.com 兜底） |
| objects.githubusercontent.com | 原样 + 经 `https://ghfast.top/{原URL}`（release 资产加速） |
| huggingface.co / hf.co | `https://hf-mirror.com/{原URL去掉huggingface.co}`（resolve 直链可换 host 前缀） |
| download.pytorch.org | 原样（国内可达，不做镜像） |
| modelscope.cn / opendatalab.com | 原样登记域名；若 403/需登录则跳过并记录（不在本版做登录会话） |

**注册表 `DATASET_REGISTRY`（任务族 → 候选；仅样例档可自动，其余只提示）**：
- det 族样例（YOLO 形态 images/ + labels/ 同级）：`https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip`（≈7MB，自动档）＋镜像派生（ghfast.top 前缀）。VOC/COCO 全量一律只列提示。
- gan/cls 族样例（≤100MB 自动档）：CIFAR-10 python 包直链镜像（如 `https://hf-mirror.com/datasets/...`）——URL 以实测可达回填为准，实施时用云端 HEAD 探针验证一次后写入 registry（探测不可达则该族只提示不自动）。
- neu/crack/defect 工业身份词命中时：注册表登记 NEU-DET 类镜像（≤1GB 档需确认，不自动）。
- 注册表条目 schema：`{"key": {"family": "...", "kind": "yolo|tar-dir|raw", "url": "...", "mirrors": [...], "size_mb": int, "auto": bool, "license": "..."}}`。

**探测择优（远端实现）**：每候选 HEAD（timeout 8s）：记录 Content-Length/可断点(Accept-Ranges)/终态 URL；跳过条件：HTTP≥400、需登录、预估 >2GB；排序 = 可断点优先 → 声明体积小优先 → 顺序；全部 HEAD 失败则退化直接 GET 首候选（一次机会）。总探测预算 ≤60s。

## 四、下载引擎终版

全部收敛为云端自包含脚本内的三兄弟纯函数（py3.10，标准库）：
1. `def _safe_download(url, dest, budget_gb)`：HEAD 预算 → GET 流式（逐块计数，实收封顶 = min(2.0, free_gb−1.5)；每 30s 打印 `[数据集] 下载中 已用 Xs 已下载 A MB / 总量 B MB`）→ 落 `.part` 完成后 `rename`；重定向仅跟随 http(s)（拒绝 file/ftp）；失败清理 .part。默认单源单包上限 2GB（>2GB 拒绝并提示）；每源 3 次重试（HTTPError 429/5xx 退避 3s；连续 60s <10KB/s 熔断切源）。
2. `def _safe_extract(archive, dest)`：magic bytes/zipfile.is_zipfile/tarfile.is_tarfile 判定（覆盖 zip/tar/tar.gz/tgz/tar.bz2/tar.xz；.7z 探测 p7zip，无则报"需要 p7zip，可改填 zip/tar 直链"）。**逐成员**校验：`(dest/name).resolve().is_relative_to(dest.resolve())`、拒绝 `..` 段/绝对路径/盘符/UNC/符号链接/设备文件（zip-slip）；**禁用 `extractall`**；压缩炸弹闸门：总解压字节 ≤ min(3×包大小, 6GB) 且成员数 ≤10 万，超限删包并报 ARCHIVE_INVALID。
3. `def _try_sources(urls, ...)`：按 §三 排序后逐源 `_safe_download`+`_safe_extract`；聚合各源错误文本，成功后写 `source_url` 到载荷，全败抛统一 SystemExit（携带原因码文本与 candidates_tried）。

URL 形态识别表（下载前分支）：普通 http(s) 包 → 上述流；HF 直链（host 含 huggingface.co 且路径含 /resolve/）→ 镜像派生后同上；ModelScope/OpenDataLab（需登录签名）→ HEAD 探测 403 则跳过并登记"需登录"，不尝试会话；末尾带 token/`?response-content` 参数的 URL 直接判 USER_INPUT_FAILED 提示换源。

## 五、接入点与改造清单（c 裁决；文件/函数/命令 旧→新）

- **dataset_discovery.py（主战场）**：`build_remote_script()` 顶部（`def load_candidate` 之后）插入三兄弟纯函数与 `_derive_mirrors`、`DATASET_REGISTRY`、`_probe_candidates`、reason_code 帮助常量；URL 直链分支（_URL_DL_B64 与 _url_ds_helper.py 内 exec 块）整体替换为"解析多候选 → `_try_sources` → YAML 定位/生成（既有逻辑复用）"；YAML download 分支（约 128-172 行）把 `urlopen(GET)`+两处 `extractall`/`filter='data'` 换成 `_try_sources([download]+镜像)` + `_safe_extract`（**删除 `filter='data'`**——py3.10 必 TypeError）；README 无 YAML 分支（82-88 行 SystemExit hint）改为"身份词命中且候选唯一 → 自动尝试；否则 payload 携带 dataset_links[:3] 由降级层展示"；0 命中单候选空档修复：唯一候选 0 命中时不再自动选中，改提示填 YAML/URL。
- **remote_runner.py**：443-466 dataset 步骤调用不动（build_remote_command 签名不变）；`.dep_dataset.py` 执行失败降级分支文案保留；963 行 execute 端 degrade 兜底字典追加 reason_code="REPO_NO_CONFIG"、suggested_actions 两条、candidates_tried=[]（仅当载荷缺失时）。
- **app.py**：756 行 data_config help 重写：支持"换行或分号分隔多直链自动择优；YAML 路径请单条；系统会在域名不可达时自动尝试 ghfast.top / hf-mirror.com 等镜像；单包上限 2GB"；降级结果卡（454-455、473-475）在有新字段时渲染原因码 + 前 3 候选 + 两条建议动作（复制按钮）；无新字段时沿用旧文案。
- **UI 文案纪律**：全中文、无 emoji；help 末尾一行许可提醒："请仅使用你有权使用的公开数据集。"

## 六、安全与体积兜底（e 裁定数值，全部采纳）

1. 自动下载门槛：score≥2 且候选唯一 → 自动；score=1 → 只提示；score=0 → degrade 原文案。
2. 单包上限 2GB（>2GB 拒绝仅提示）；分档：≤100MB 自动样例档 / 100MB–1GB 需确认 / 1–2GB 需确认 / >2GB 拒绝。
3. 下载前预算：目标盘 free ≥ 2×Content-Length + 1.5GB（保留既有 1.5GB 硬下限）。
4. 解压炸弹闸门：总字节 ≤ min(3×包大小, 6GB)、成员 ≤10 万。
5. 重定向仅 http(s) scheme。
6. 目标目录：默认 repo/datasets；磁盘余量 <2GB 时切 `/root/autodl-tmp/datasets` 并写绝对路径 YAML（开关 `PAPER_REPRO_DATA_HOME`）。
7. 失败清理：.part/.unpacking_*/archive 一律删除；步骤成功/降级收尾输出 `[数据集] 磁盘占用 datasets=X GB 可用=Y GB`。
8. 半截隔离：下载写 `.part`、解压进 `.unpacking_<name>/`，校验齐备后改名。

## 七、实施顺序与验收（不做清单）

**P0（止血，一次提交）**：py3.10 tar 修复（删 filter='data' 换 _safe_extract）；zip-slip/炸弹闸门/重定向 scheme 三安全件；URL 多候选拆分（换行|分号）与 _derive_mirrors；degrade 载荷追加字段。
验收：tests 新增 8 条全绿（镜像派生、zip-slip 拒绝、解压炸弹闸门、多候选拆分、reason_code 兜底、extract_payload 兼容新键、registry schema、bash -n 全步骤）；pytest 88 全绿（新增后 96±）；AppTest 0 异常。
**P1**：注册表（coco128 起，AutoDL 云端 HEAD 探针实测回填）；README 高置信自动/候选提示；YAML download 分支镜像回退；UI help 与降级卡新字段渲染。
验收：dataset 步骤在 PyTorch-GAN 类仓库（无数据）以 auto 模式在真实 AutoDL 实例跑通：不再 degrade 或 degrade 但给出可复制候选；有数据集时训练启动并回传 source_url。真机 e2e 用新服务器 `connect.cqa1.seetacloud.com:22880`（root/内存密码）跑 safe→auto 两轮。
**P2**：数据盘自动切换 PAPER_REPRO_DATA_HOME；下载进度回传增强（30s 节流已有，补 5% 档位）；候选源可达性快照回填（curl -I 批量探针脚本写入 registry）。
验收：全绿 + 双实例 e2e + 磁盘占用汇报。
**不做清单**：不做 Kaggle/需登录源自动会话；不引入 aria2 强依赖（可选探测）；不改 build_remote_command 公共签名；不动 degrade 标记/载荷旧键/自包含脚本测试锁点；不自动下载 VOC/COCO 全量/ImageNet/CelebA；不在云端引入 bs4/requests（纯标准库+可选 PyYAML）；不做本地在线爬虫扩展（repo_crawler 保持现状）。
