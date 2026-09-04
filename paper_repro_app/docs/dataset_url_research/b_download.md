# b_download 远端下载引擎与解压健壮性规范（下载/解压架构师）

适用范围：dataset 步骤的远端 Python 脚本（DatasetDiscovery.build_remote_script 生成的源码块）与 build_remote_command 的命令拼接。约束：UI 中文无 emoji；云端仅 Python 标准库 + requests + zipfile/tarfile（curl/wget/aria2 只探测可选）；pytest 88 全绿与 AppTest 0 异常不回归；口令与 URL 敏感参数不得写入日志。

## 决策

### 1. 下载命令设计（bash+python 混合，默认零新依赖）

- 单一 Python 驱动负责全流程（预检 → 下载 → 校验 → 解压 → 布局），bash 只做环境探测与命令兜底。理由：进度分片输出、熔断计时、超时预算、校验、解压全部要共享同一状态机，混在多条 bash 命令里必然失控。
- 后端选择（auto 模式，探测即用，不安装任何新包）：优先 requests 流式，回退 urllib.request 流式；两者都支持 Range 续传与读写超时。特殊模式：探测到 aria2c 且（文件 ≥200MB 且服务器返回 Accept-Ranges: bytes）时启用 -x5 -s5 分片加速；curl -C - 仅保留为诊断与显式 curl 模式（--speed-time/--speed-limit 语义在 Python 驱动内等价实现）。默认单流，理由：大多数训练数据包在 1-8GB 区间，单流+续传已足够，分片只在带宽瓶颈且源站支持分段时才值得引入，避免多连被源站限速。
- 重定向：跟随上限 10 跳，记录最终 URL 归属域。HF/ModelScope 等跳到对象存储签名域属正常跳转，不算异常；只有最终域无法归类且响应非归档时才降级为“HTML/未知形态”处理。
- 限速规避：默认单连接、UA 伪装成常规浏览器、命中 429 或 Retry-After 时指数退避（2/5/10s）重试，不并发轰炸源站。
- 低网速熔断：每 10 秒采样一次均速，连续 60 秒 <10KB/s → 终止本轮并标记“慢源”，按候选次序切换镜像；最多切 2 次，仍慢则给“慢源熔断”文案。
- 断点续传：任何中断保留 .part 文件，下一轮用 Range: bytes=N- 续传；5xx/断流类瞬时错误重试 ≤3 次（退避 2/5/10s）。
- 磁盘预检（下载前必做）：HEAD 取 Content-Length；拿不到按未知长度处理，靠每 30s 落盘字节数撞硬上限强停。所需空间 = 包大小 ×2.2 + 1GB（包 + 解压 + 余量），df 目标盘比对；不足则自动切 /root/autodl-tmp（AutoDL 数据盘，探测存在且可写则优先），否则工作区 .paper_repro_dl；双盘均不足 → “磁盘满”文案。解压完成后删除归档回收空间。
- 单文件上限：默认 20GB（PAPER_REPRO_MAX_DL_GB 可调，可覆盖 COCO 级大包），超限即拒并建议换镜像/分卷直链；未知长度以落盘字节撞上限为准。
- 换源次序（失败即降级不放弃）：用户直链 → 同域镜像孪生（hf-mirror.com 等）→ 自动发现候选（与 a_sources 联动）；换源时同文件续传、不重新下载。

### 2. 解压矩阵与安全解压

- 归档类型判定以 magic bytes 为准、后缀仅作提示；两者冲突以 magic 为准并记 warning。识别表：zip=PK\x03\x04；gzip=\x1f\x8b（解流后 257 偏移查 ustar 区分 tar.gz 与纯 .gz）；bzip2=BZh（同法查 tar.bz2）；xz=\xfd7zXZ\x00（查 tar.xz）；7z=7z\xbc\xaf\x27\x1c；裸 tar=257 偏移 'ustar'。
- 支持矩阵：zip、tar、tar.gz、tgz、tar.bz2、tar.xz 全部 Python 原生（zipfile/tarfile）零依赖；.7z 仅当探测到 7z/7za/7zr 二进制时执行（7z x -y），否则给出“需 p7zip”明确文案并建议换 zip/tar 镜像；纯 .gz 数据文件视为不支持并说明。
- 安全解压（zip-slip 防护）：逐成员遍历，禁用 extractall。任一成员命中以下规则即中止整个解压并记录（名称截断防刷屏）：含 .. 路径段、绝对路径、Windows 盘符或反斜杠路径注入；tar 符号/硬链接指向根外（或整体跳过链接成员）。附加防线：成员数 ≤20 万个、累计解压量不得超过剩余磁盘，防压缩炸弹。
- 布局规范化：单顶层目录剥离（根下仅 1 个目录且根级普通文件 ≤3 个则上移一层作为数据根）；深度 ≤3 扫描定位 images 目录（images/image/imgs/JPEGImages 等白名单+包含匹配）与 labels 目录（labels/label；annotations 目录内为 .txt 则 YOLO 标注、为 .json/.xml 则记 coco/voc 风格交下游 YAML 生成，不在本步强转）；无 val 目录 → val 复用 train（沿用既有帮助文案语义）。输出 {root, images_dir, labels_dir, is_yolo_layout, annotations_style}。

### 3. 进度、超时与失败原因分级

- 进度输出：下载与解压期间每 30 秒一行 DS_DL|stage|…（DS_DL|progress|bytes=N|total=M|pct=P|kbps=K；DS_DL|unpack|done=N|total=M），不秒级刷屏；extract_payload 将 DS_DL 行归并进结果 download 段，前端照旧展示。
- 超时预算：单数据集步骤默认 15 分钟（PAPER_REPRO_DL_TIMEOUT_SEC=900，可配），同时受“单步执行超时”上限截断；预算按整个候选轮次累计计算。
- 失败分级文案（作为 dataset.degraded 的 reason 常量表，中文无 emoji）：
  - 404：“数据集直链返回 404（地址不存在），已自动尝试候选源；仍失败请核对直链或改用自动发现”；
  - 403：“服务器拒绝访问（403）：该直链可能需要登录、带签名参数或受防盗链限制，已换镜像重试一次”；
  - 超时：“下载超时（预算 N 分钟）：到该源网络过慢，已切换镜像；可增大超时后重试”；
  - 磁盘满：“磁盘空间不足：需 X GB 剩 Y GB；已清理临时文件，建议将数据放到 /root/autodl-tmp 数据盘”；
  - 解压失败：“解压失败（阶段 X）：归档可能损坏或格式不支持；建议开启 sha256 校验后重试”；
  - 校验失败：“SHA256 不一致（期望 abcd… 实际 ef12…）：已自动重下第 N/3 次”；
  - 慢源熔断：“源站速度过低（连续 60 秒低于 10KB/s），已自动切换候选源”。

### 4. 校验与重下策略

- 校验来源优先级：URL 片段 #sha256=<64hex> → 用户随数据包提供的 .sha256 文件 → 下载成功后自动探测相邻 url+.sha256（GET 前 512 字节提取十六进制串）；均无则只记录计算值供审计与下次复用比对。
- 下载过程流式累计 sha256（不二次读盘）；比对失败 → 删除 .part 全量重下，最多 3 轮；仍失败按“校验失败”文案处理，残缺文件以 .bad 后缀保留备人工核对。缓存复用：同 URL 缓存文件 sha256 一致时跳过下载直接解压。

### 5. 用户 URL 形态识别表（结论）

| 形态 | 判定法 | 处理结论 |
| --- | --- | --- |
| 裸文件直链 | 扩展名或 Content-Type/Content-Disposition 为归档 | 直接进入下载管线 |
| 重定向链 | 响应状态序列 | 跟随 ≤10 跳并记录最终域；签名 CDN 跳转属正常 |
| HTML 页面 | Content-Type: text/html | 域归一化后处理：GitHub 仓库/分支页 → 补 /archive/refs/heads/{默认分支}.zip；GitHub release 页 → 取首个大体积 asset 直链；HF 数据集页 → 拼 resolve/main/ 模板；ModelScope 数据集页 → 转 api repo 端点；OpenDataLab/OpenXLab 门户页 → 需登录生成 OSS 签名直链，给“请在页面点击下载后粘贴真实直链”引导文案；其它域 → 页内提取归档链接，仅当唯一候选才自动下载，多候选则提示人工指定 |
| HF resolve URL | 路径含 /datasets/{o}/{n}/resolve/ | 先直连官方；403/超时/慢源时切 hf-mirror.com 同路径孪生 |
| ModelScope 文件 URL | 含 /file/view/ 或 api/v1/datasets/…/repo?FilePath= | 统一转 api GET（Revision 默认 master）流式下载 |
| OpenDataLab/OpenXLab 分享链接 | 门户域名 | 不支持匿名直连：识别后引导粘贴其签名 OSS 直链；自动发现侧仍可命中官方可直下镜像 |
| 网盘/云盘分享页 | 需登录或强限速 | 直接“该链接类型暂不支持，请换直链或开源镜像” |

## 可执行变更

1. 在 DatasetDiscovery.build_remote_script 生成的数据集脚本头部注入 DL_ENGINE 源码块（纯 stdlib + 条件 requests）：函数 pick_backend、head_probe、download_stream、hash_sha256、detect_archive、unpack_safe、normalize_layout、mirror_plan、classify_error；全流程异常统一收敛为 outcome dict，不裸抛。
2. build_remote_command(python_bin, data_config) 透传环境变量：PAPER_REPRO_DL_TIMEOUT_SEC=900、PAPER_REPRO_MAX_DL_GB=20、PAPER_REPRO_DL_DIR（默认 /root/autodl-tmp/paper_repro_dl，不可写则回退工作区 .paper_repro_dl）、PAPER_REPRO_DL_MODE=auto；不改动 UI 控件即零 AppTest 风险，上述值均可由云端 env 覆盖。
3. data_config 为 http(s) 直链时执行新分支：mirror_plan 生成候选列表 → 逐候选下载（含预检/续传/熔断/预算）→ 校验 → unpack_safe → normalize_layout → 写 .paper_repro_dataset.env 与 PAPER_REPRO_DATA_CONFIG；与既有“自动发现”分支共用后半段，保证 YAML 生成与训练入口识别逻辑不重复实现。
4. dataset 结果 dict 扩展字段（extract_payload 兼容旧字段，新增 download 段）：url_family、attempts[{host,status,ms,method}]、bytes、sha256_ok、archive_type、unpack_ok、layout{root,images_dir,labels_dir,is_yolo_layout}、degraded、reason；reason 取自“决策 3”常量表。
5. 日志约定：关键事件一律 DS_DL| 前缀，每 30s 至少一行；extract_payload 增加 DS_DL 行解析，下载/解压失败时 failed_step=dataset，供前端错误定位复用。
6. URL 敏感净化：日志回显 URL 前剥离 userinfo 与 query 取值（仅留 scheme://host/path），密码与签名参数不外泄。
7. 清理与缓存：解压成功后删除归档与 .part；磁盘满/校验失败分支按文案动作清理；同任务重试时命中缓存且 sha256 一致则直接解压跳过下载。
8. 文案与测试联动（回归门槛：pytest 88 全绿、AppTest 0 异常）：data_config help 尾补“支持 URL 后加 #sha256=<64hex> 自动校验”；“自动发现失败未训练”降级提示补“可填写直链（含镜像自动切换）后重试”；为 mirror_plan 的 6 类 URL 形态与解压安全拒绝路径各补单元测试。
