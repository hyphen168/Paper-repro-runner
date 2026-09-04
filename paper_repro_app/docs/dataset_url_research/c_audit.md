## 审计报告：数据集"自动找源 + URL 下载兜底"接入点清单与改造边界

**说明：本审计官仅有只读工具（无写盘工具），按任务约定将全文放最终回复；建议父任务将其落盘为 `docs/dataset_url_research/a_sources.md ~ lead_spec.md`。**

### 一、现状能力清单（以文件复核为准）

**1. 用户 URL 直链支持程度。** 触发链：app.py:756 `data_config` 文本输入 → app.py:955 提交进任务 → remote_runner.py:443-444 `data_config` 提取、`requires_dataset = bool(configured_run_command or self.auto_run)` → :447 且 `auto_download_dataset` 默认 True（app.py:779）时执行 dataset 步骤 → remote_runner.py:459 调 `DatasetDiscovery.build_remote_command("\"$PYTHON_BIN\"", data_config)`。dataset_discovery.py:182-190 的 `build_remote_command` 用 base64 落盘 `.dep_dataset.py` 后 `python .dep_dataset.py {data_config!r}` 执行。云端脚本能力（dataset_discovery.py:45-62 生成串内）：
- 下载：`urllib.request` + 3 次重试、单次超时 **600 秒**（写死）、`shutil.copyfileobj` 流式落盘；HTTPError 301/302/303/307/308 手动跟随 Location（3.10 不自动跟 308）；磁盘检查 `<1.5GB` 拒绝下载。
- 解压：`zipfile.is_zipfile` 全量解压 / `tarfile`（`filter='data'`），非 ZIP/TAR 即删除并 SystemExit。
- 找配置：先 `data_home.rglob('*.yaml')` 用 `load_candidate`（要求 train+val 字段）；无则扫描 `images/train+val` 与 `labels/` 目录结构、从 label txt 反推 `nc`，生成 `paper_repro_auto.yaml`（绝对 path、无 val 时复用 train）。随后外层 `if requested:` 走 YAML 加载与缺失时官方下载（YAML 须声明 `download:`，HTTP 源同样 600s 超时/3 次重试，另有 HEAD 预检 Content-Length>剩余空间 80% 拦截；非 HTTP download 会当 shell 命令或注入 `PAPER_REPRO_HELPER_CONFIG` 的 python 片段执行，dataset_discovery.py:8-30、:155-171）。成功写 `.paper_repro_dataset.env`（:176）与 `PAPER_REPRO_DATASET_JSON` 载荷（:177-178）。
- 划分：data_split 非空时 remote_runner.py:468-486 追加 split 段（软链接划分+重写 env），仅在 dataset 步骤成功后经 `&&` 串接。

**2. "自动发现"现在做什么。** `data_config` 为空 → dataset_discovery.py:71-95 else 分支：以 `Path.cwd().name` 拆词作 identity（:72），`root.rglob('*.yaml')` 全仓库扫描（排除 .git/.venv/venv），`load_candidate` 只收含 train/val 的 YAML，排序键为"身份命中 > 是否声明 download > 路径深度 > 字母序"（:88-91）。README 的 http 链接只在无 YAML 时被正则抽取成 `hint` 文本后 SystemExit（:82-88），**只提示、不尝试**。

**3. degraded 触发条件。** remote_runner.py:447 `degrade_on_missing = auto_run and not configured_run_command`（auto/tune 且无自定义命令）；数据集脚本任一路径 SystemExit（无匹配 YAML/无 download 声明/下载失败/空间不足）→ :461-463 打印 `[paper-repro-degrade]`、`touch .paper_repro_dataset_missing`、`exit 0` → run 步骤 :551-560 检测 marker 后只做入口安全检查 → :962-963 `dataset = {"degraded": True, "reason": "仓库无匹配数据集配置或下载不可用，已自动降级为安全检查（未训练）"}`，与 task-a51308f3 观察一致。UI 侧 app.py:454-455 展示 warning + caption，app.py:473-475 JSON 展开。run 模式（带命令）下走 `[paper-repro-degrade-fatal]` 直接失败（:465-466）。

### 二、缺口清单（对照用户诉求逐条）

1. **用户 URL 下载失败无回退**：下载循环（dataset_discovery.py:61 内嵌块与 :128-152 官方 download 段）只对一个 URL 重试 3 次，失败即 SystemExit；无 clone 步骤那种"官方 ↔ ghfast.top"备源互换（remote_runner.py:644-652）或 pip 式多源链。
2. **无候选源列表择优**：没有多源可达性探测、无"按域名生成镜像候选"逻辑（github.com→ghfast.top/https://github.com/…、huggingface.co→hf-mirror.com 等），无来源级降级与 `payload['source_url']` 记录。
3. **README/配置链接未抽取利用**：dataset_discovery.py:82-88 抽取的 `dataset_links[:3]` 只进 hint 文本，从未作为下载候选；identity 匹配既防误下（好）也未用于"自动找源"。
4. **无下载进度/超时可配/续传**：600s 写死；无 `Content-Length` 进度输出（仅有 `copyfileobj` 无显示）；无 curl `-C -`/aria2 探测续传；系统盘 30G 约束下无下载后缓存复用（`datasets/` 每次全新下载，仅磁盘空间拦截）。
5. **HF/ModelScope/OpenDataLab 不支持**：云端脚本仅 urllib 裸下载 + ZIP/TAR，无 HF datasets/ModelScope 直链解析，国内可达源零接入；本次 PyTorch-GAN 场景正是此类。
6. **degrade 文案不可操作**：remote_runner.py:963 固定 reason、app.py:454-455 只让用户"填 YAML"，未回传已发现的 README 链接/候选，用户无从下手。

### 三、接入点与最小侵入改造边界

- **新增代码位置**：留在 `dataset_discovery.py` 的 `DatasetDiscovery.build_remote_script` 生成的云端自包含脚本内（唯一事实源；test_basic.py:364-387 锁定自包含）。不建议新建本地模块做在线爬取——云端执行时本地 `requests/bs4` 不可用、且违背"云端仅标准库+requests"硬约束；本地侧 repo_crawler.py 已有 `AutoRepoDatasetCrawler`（:25）但那是仓库/数据集候选爬虫（GitHub API），只跑在本机、结果过 `clone_url` 通道，可作为"本地预调研 → 注入候选"的可选增强，与云端回退解耦。
- **改造点 1（核心）**：在云端脚本 URL 分支前插入纯函数 `def _derive_mirrors(url): ...`（按域名前缀替换生成 2-3 个镜像 URL）与 `def _try_sources(urls): ...`（逐源 urllib 下载，聚合各源错误后统一 SystemExit），下载/解压/YAML 生成逻辑复用现有 exec 块（dataset_discovery.py:61），仅把"单 URL"换为"有序候选 + 记录 source_url 进 payload"。
- **改造点 2**：`identity` 命中（:72）后若 YAML 缺失，把 README 抽取的 `dataset_links` 过滤为"匹配 identity 且为 zip/tar/github-release 域"的 URL 作为自动候选（保留 :88 的多候选需人工确认防线，仅当候选唯一且命中身份词才自动尝试，防 Argoverse 类误下）；加 `known_dataset_registry`（coco128/NEU-DET/CelebA 等常见键 → 国内镜像 URL 表）。
- **改造点 3（命令处）**：remote_runner.py:448-464 dataset_step 需给 `build_remote_command` 增加可选第二参数（候选 URL 列表经 sys.argv[2] 或环境变量传入，**不改 build_remote_command 签名以外的调用面**，python `!r` 引号已在 :188 走通）；降级分支保持 :460-466 不变。
- **改造点 4（UI 语义）**：`auto_download_dataset`（app.py:779）语义扩展为"缺失时自动寻找并下载（含镜像回退）"与现行为完全兼容——它本来就是 dataset 步骤总闸（remote_runner.py:447 `if requires_dataset and ...`），True 分支内容加强即可；False 分支（:487-491）保持"仅 find 扫描"。新增"数据源候选"仅建议放高级折叠区（app.py:747 内），不占用 data_config 单行。
- **改造点 5（文案）**：remote_runner.py:963 reason 与 app.py:454-455 提示改为可操作：附上"已尝试源 + 失败原因摘要 + 建议填入 ghfast.top/hf-mirror 前缀的直链"，app.py:756 help 增补镜像前缀示例；数据集 JSON 增加 `attempts/source_url/candidates` 供 app.py:475 展示。

### 四、单测与 e2e 验证点

- tests/test_basic.py 扩展：`build_remote_script()` 断言含 `_derive_mirrors`/多源错误聚合；`extract_payload` 对含 `source_url` 新键载荷可还原（沿用 :380-383 模式）；全步骤 `bash -n` 校验（test_basic.py:190-220）保证 dataset 命令语法不回退。
- 新增本地可跑用例：临时仓库 + 本地 `http.server` fixture，实际执行 `.dep_dataset.py`（PyYAML 本机已具备），覆盖"首源 404→次源成功"与"全源失败→SystemExit 文案"；不依赖真实云机。
- e2e：scripts/e2e_task.py 对真实 AutoDL 实例跑 `--mode auto`，断言 ① 仓库无数据时不再 degraded 而是训练启动；② 结果 JSON dataset 含 `source_url`；③ AppTest/pytest 88 全绿不回归。

### 审计结论
无代码改动可审，属规划审计。现状代码（dataset_discovery.py、remote_runner.py:443-466/962-963、app.py:756/779/454-455）与观察日志完全一致，降级链路行为正确；缺口均为增强项而非缺陷。最小改造边界清晰：**全部逻辑收敛于 dataset_discovery.build_remote_script 生成的云端脚本 + remote_runner.py:459 一处调用 + app.py 文案**，不引入新依赖、不动 DB 结构、不触碰降级安全网。

Merge verdict：OK with notes（改造建议见第三/四节，实施前需跑 test_basic 全量与 bash -n）。