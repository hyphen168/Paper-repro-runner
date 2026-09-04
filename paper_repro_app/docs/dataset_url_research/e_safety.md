已按任务要求完成对 `dataset_discovery.py`（URL 直链分支 = `_url_ds_helper.py` 经 base64 exec 注入）、`remote_runner.py`（dataset/降级链路、conda 自举 python=3.10）、`app.py`（高级选项 747-790）与 tests 的源码复核。无法写盘（本评审无写文件工具），故按约定全文放在本回复，供写入 `docs/dataset_url_research/e_safety.md`。

---

## 风险与裁定

**1) 自动寻源误伤面（置信度门槛）。** 现状已有部分防线：`dataset_discovery.py` build_remote_script 空配置分支按"仓库目录名拆身份词 → rglob YAML 含 train/val → 排序（命中数/是否声明 download/层级/字母序）"，且"身份词存在、多候选全部 0 命中"会拒绝并提示。但有两个空档：①唯一候选 0 命中仍会被选中并可能执行其 download: 指令；②README 里的 dataset 链接目前只进提示不进下载（好）。**新增外部自动寻源的误伤面是任务类型推断错误**：仓库内无 YAML、README 无链接时按 GAN/检测/分类猜数据集，猜错一次即浪费 10 分钟+磁盘与一次训练失败。**裁定：自动下载只允许在"主题强命中且证据唯一"时发生，外部源一律默认"只提示、等用户填 URL"**。给出数值门槛：令 score = 类型词在 目录名/README/代码 import 中命中数（每处 +1，同一词去重）；score≥2 且候选唯一才可自动下载；score=1 仅提示候选清单；score=0 维持 degrade（现有文案）。检测/分割类大集（VOC/COCO/ImageNet）不论 score 一律不自动下载，仅列镜像链接。

**2) 安全（远端=用户自有云机，SSRF 面小，但仍需防以下 5 项）。**
a) HTML 误当文件：已有兜底（下载后 is_zipfile/is_tarfile 双检，非包即删并报错），判定已覆盖，无需按 MIME 加逻辑。
b) **zip-slip：真实缺口**。URL 分支与 YAML download 分支均直接 `ZipFile.extractall(data_home/base.parent)`，无成员名校验；Python zipfile 不拦 `../` 与盘符段，恶意包可越界写 repo 及上层、覆盖训练脚本。另注意：tar 分支写 `extractall(..., filter='data')`，该参数 Python 3.12 才引入，而 conda 自举钉死 `python=3.10`（remote_runner.py:262），走到 TAR 下载会直接 TypeError 崩，等于"伪防护 + 真故障"。
c) 压缩炸弹：无解压总字节/条数闸门，需新增。
d) Content-Length 谎报：仅 YAML 分支做了 HEAD 预算（>free×0.8 拒）；URL 直链分支无 HEAD、下载无字节计数，`copyfileobj` 可把磁盘写满。
e) 重定向 Location 未校验 scheme：`_dl = headers['Location']` 后直接 `urllib.request`（支持 file/ftp），仅允许跟随 http(s)。
f) 失败路径不清理半截文件，残留占盘。
**裁定：以上除 (a) 外均需在落地代码前补齐（见兜底清单第 3-8 条）；文案可标注"公开数据集请核对原许可后使用"，仅 UI help/报告一行，中文无 emoji。**

**3) 体积/成本预算。** AutoDL 系统盘 30G（conda/pip 缓存同盘），`remote_workdir` 默认已落 `/root/autodl-tmp` 数据盘；但数据集 `datasets/` 跟随工作目录，若用户把工作目录改到 /root 就落系统盘——需运行时实测 `shutil.disk_usage` 而非假设。**裁定数值：默认单包上限 2GB**（覆盖 coco128≈7MB、CelebA≈1.4G；VOC trainval≈1.9G 临界，归入"需一次确认"档）；>2GB 一律拒绝并提示。下载前置预算：目标盘 free ≥ 2×Content-Length + 1.5GB 硬下限（保留现值）；下载中用实收字节数封顶 = min(2GB, free-1.5GB)，超限即中止并删除。成本闸门：2GB@常见 5-10MB/s 约 4-7 分钟/次、失败重试 3 次内闭环；单包上限即流量与时间的第一道闸。

**4) 许可提醒位置。** 仅两处文案：高级选项"数据集"输入框 help 追加一句、任务详情 degraded/提示区一行；不阻断、不校验。

## 兜底规则清单

1. **自动下载前置条件（置信门槛）**：score≥2 且候选唯一，否则只提示不下载；degrade 分支保留并展示 README/候选源链接（各≤3 条）。
2. **修正单候选 0 命中空档**：身份词存在且唯一候选 0 命中时，从"选中"改为"提示用户填 YAML/URL"，不执行该候选 download:。
3. **统一安全解压函数（替代两处 extractall）**：py3.10 兼容——zip/tar 逐成员校验：`(目标/成员名).resolve()` 必须在解压根内、拒绝 `..` 段/绝对路径/盘符/UNC/设备文件/symlink；tar 不再依赖 `filter='data'` 参数；须与 `_url_ds_helper.py` 同源 b64 单例（避免旧版残留双份）。
4. **压缩炸弹闸门**：解压总字节 ≤ min(3×包大小, 6GB)，条目数 ≤ 10 万；超限即删包中止并报错提示换小数据集。
5. **Content-Length 防谎报**：先 HEAD 取 Content-Length 与跳转终态；下载逐块计数，实收 > 封顶即中止；落盘后校验实收 ≤ 声明值×1.1（容忍差值），否则删除重试一次后报错。
6. **磁盘硬预算**：下载前 `free(目标盘) ≥ 2×声明包大小 + 1.5GB`（下限不变）；目标目录优先数据盘，工作目录在系统盘时自动建议改址。
7. **重定向约束**：仅跟随 http(s) Location，拒绝 file/ftp 等 scheme；每包 3 次重试、单次 600s 超时不变。
8. **失败清理**：任何下载/解压失败路径 `archive.unlink(missing_ok=True)` 并清理半截解压目录。
9. **体积分档交互**：≤1GB 高置信可自动；1-2GB 需提交前确认一次；>2GB 拒绝，仅列提示。
10. **许可文案**：仅 UI help 与报告各一行（无 emoji，不阻断）。
11. **回归护栏**：改动集中在 dataset 脚本常量后跑 pytest 88 全绿 + AppTest 0 异常 + 云端 3.10 实机 tar/zip 冒烟（本轮未跑，需 supervisor 在落地代码后执行）。

**代码证据**：`dataset_discovery.py:33`（_URL_DL_B64=URL 分支：无 HEAD、无字节计数、`_z.extractall(data_home)`、失败不清理）；`build_remote_script()` 内 URL 下载段 `tarfile.extractall(..., filter='data')`（3.12+ API）、0 命中单候选无拦截、README 链接仅提示；`dataset_discovery.py:118`（唯一 Content-Length 预算）；`remote_runner.py:262`（python=3.10）、`:445-463`（dataset 步骤与 degrade 结构）、`:961-963`（degraded 标记，与 task-a51308f3 日志一致）；`app.py:777-779`（data_config 与 auto_download_dataset UI）。

## Review
- Correct：现有"0 命中多候选拒绝 + README 链接仅提示 + 下载后类型校验 + 1.5GB 磁盘下限 + degrade 不假死"是良好地基，本次建议应在其上加闸门而非推翻。
- Finding：P1 ×4 —— tar `filter='data'` 在钉死 3.10 的环境必 TypeError（TAR 直链/仓库 TAR 下载整条不可用）；zip-slip 无校验；URL 分支无字节封顶可写满盘；重定向未限 scheme。均为新方案落地前必须补的项（规则 3/5/6/7）。
- Merge verdict：OK with notes（评审结论可并入 e_safety.md；规则 3-8 属实现前置条件，代码改动后须按规则 11 复跑回归与云端冒烟）。