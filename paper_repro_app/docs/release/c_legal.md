# 专家组·合规与文档审计报告（许可/隐私/版权完整性）

审计范围：依赖清单、pyproject/README、make_dist.py FRIEND_GUIDE、paper_claims.json、天气/IP/昼夜/SSH/任务编排/远端流水线/数据集下载各模块、start_app.*、GUIDE 与 docs 抽样、tests/scripts 抽样。结论先行：**无实质性阻断项，可交付**；但发布前建议补三件小事（见文末）。

## 1) 依赖许可面（结论：通过，需补 NOTICE）

- 自研代码声明 MIT（pyproject license={text:"MIT"}），但**根目录无 LICENSE 文件**、无作者版权行，建议随包补 `LICENSE(MIT)`。
- 9 个锁定依赖均为宽松许可：streamlit(Apache-2.0)、pandas/numpy(BSD-3)、requests(Apache-2.0)、beautifulsoup4/PyYAML/pydantic/pytest(MIT)。**唯一例外 paramiko 为 LGPL-2.1**（弱 copyleft）。分发形态是"zip 源码+说明，依赖由朋友侧 pip 安装"，不重分发 wheel/二进制，LGPL 义务由 pip 安装场景正常满足；仍建议在 THIRD-PARTY/NOTICE 中列名。
- zip 由 make_dist 排除 .venv/data/logs/assets/.git 等，不含第三方字体/图标/二进制资源，**无随包 license 义务的实体文件**；各依赖许可元数据随 pip 装进用户 venv 的 site-packages，与 zip 无涉。
- 提示：requirements 用 `==` 锁 2026 版（pandas 3.x 需 Py3.11+），README/FRIEND_GUIDE 已同步引导 3.11+，无冲突。

## 2) 外部服务使用声明（每项一句建议，写进使用说明"网络与隐私"小节）

- **ip-api.com**（免费档限非商用、HTTP、约 45 次/分）：用于 IP 自动定位取经纬度/城市——"为渲染当地天气会向该服务发送你的公网 IP，仅粗定位；可改手动城市避免出网"。 [weather_fx.py]
- **Open-Meteo**（api.open-meteo.com 与 geocoding-api）：发送坐标/城市名取天气与地理编码——"免费免密钥，建议保留 Data by Open-Meteo.com 署名；结果仅缓存本机 30 分钟"。 [weather_fx.py]
- **GitHub/Gitee API 与 arXiv/论文页抓取**：仓库与标题搜索，发送论文链接/关键词，匿名 API 有速率限制。 [repo_crawler.py]
- **镜像/下载源（出网主体是你自有的云主机）**：本地启动仅对清华/阿里/腾讯/中科大/华为/豆瓣+pypi.org 做 HEAD 测速（暴露本机 IP/UA）；云端流水线会访问清华 anaconda/pip 镜像、**download.pytorch.org whl/cu121、cu128**、ghfast.top 加速、GitHub/官方数据源。声明："依赖与数据下载均在你的云服务器上发起，显示其 IP；本应用无遥测、无账号回传"。
- **数据集直链**：仅允许 http(s)，已含 zip-slip/符号链接防护、磁盘≥1.5GB 预检、308 跟随与重试；但直链若带签名 token 会被记入任务日志（见 §3）。 [dataset_discovery.py]
- WMO 代码表属事实标准、NOAA 太阳算法为公开算法、昼夜为纯本地计算，无版权索取。 [day_night.py]
- GUIDE 已有"公开数据集请核对原许可后使用"一句（G-5/安全须知末行），建议在 FRIEND_GUIDE 与数据集高级选项 UI 各再补一句。

## 3) 凭据隐私声明（现状与须写明条目）

现状（证据）：tasks 表**无 password 列**；密码仅存进程内存 `_EXEC_STATE.task_passwords`，重开应用/换会话即失效，重执行须补输（G-7 与 UI 均提示）；粘贴的私钥落 `~/.ssh/paper_repro_generated|auto_generated` 且 chmod 600，**不入应用目录、不入 zip**；cloud_config.json 只存 host/user/key 路径/别名（无密码，chmod 600）。日志侧 `sanitize()` 对 PEM 全文与 `password=` 形态脱敏，回写任务记录前调用。 [database.py、ssh_utils.py、storage_utils.py、app.py]

须写明的条目（现状已满足/建议补文）：
- 密码"仅本次运行内存存活、不落盘不进日志"——建议在 FRIEND_GUIDE 安全小节成文（GUIDE G-7 已有）；
- **残余风险**：完整远端命令与数据集 URL 会明文进入 `~/.paper_repro_app/logs/app.log` 与任务 JSON（StepLogger.log_command），故应提示"勿把含密钥/签名的数据直链或命令填入应用"；
- **局域网暴露**：start_app 绑定 0.0.0.0 且 Streamlit 无登录鉴权，同网段可看任务与日志——建议在说明中写"仅在可信网络使用或关闭防火墙暴露"，或默认改回 127.0.0.1；
- **scripts/e2e_task.py**：未发现硬编码凭据（仅 docstring 残留一台历史测试机地址 connect.cqa1.seetacloud.com，已过时无害），但 `--password` 走命令行会暴露于进程列表/Shell 历史——建议分发 zip 排除 scripts/ 与 tests/，或标注"开发者专用"。

## 4) 论文数值与数据集引用规范（结论：合格，一处措辞待修）

- paper_claims.json 随包（位于包目录，会被打进 zip）。对比表逐行内联 `[source]`（如 He et al. 2016 arXiv:1512.03385 Table 2），并渲染 caliber 口径与 L1/L3 级别注记——**出处提示粒度已到 UI 表格单元格，足够**。 [storage_utils.py→build_comparison_table]
- 诚实性亮点：MNIST 条目注明 LeCun 表值仅背景；ResNet 注 56-layer 仅背景；YOLOv5 明示 coco128 3-epoch 与 COCO val2017 全量不可直接对比。
- **待修**：YOLOv5 0.287 与 MNIST 99.0 为静态占位值，而 source 标注"commit 执行期回填"，代码并未实现回填（表格直接展示该静态值）——交付前改措辞为"官方教程基线（非论文原表）"或补实现，避免出处表述与数值来源不一致。
- 数据集许可无自动核验（依赖仓库声明与用户自填），GUIDE 一句提示已覆盖最低要求；docs/ 抽样（GUIDE、day_night_research）为自撰文档，无第三方版权内容痕迹。README 引用的 product-launch-record/final-delivery-package/requirements-analysis/pipeline-upgrade-log **四文档实际不存在**（死链），且 README 目录树已过时、含真实 GitHub 账号链接（hyphen168）——交付整洁度问题，非版权风险。

## 5) README/FRIEND_GUIDE 缺失声明清单

README 与 FRIEND_GUIDE 当前均缺：①版本号与打包日期——且版本三处不一致（make_dist VERSION=1.5.0 / pyproject 0.2.0 / `__init__.__version__` 0.1.0），建议单源化；②作者可留空、联系方式可留空；③免责声明——"按现状提供，不担保复现数值与论文原文一致，云端费用与数据许可合规由使用者自负"；④MIT 许可与第三方依赖（含 paramiko LGPL）NOTICE；⑤§2/§3 的网络与隐私小节；⑥ip-api/Open-Meteo 免费档"限非商用"条款提醒。以上均为文档补充项，不涉代码改动。

## 结论

许可面全绿（补 LICENSE/NOTICE 即完美）；外部服务与隐私只需在说明中加"网络与隐私"小节（ip-api/Open-Meteo 用途、云主机出网说明、直链 token 风险、局域网提示各一句）；凭据现状已达标（内存态密码+日志脱敏），写明即可；论文出处引用达到表格粒度且口径诚实，仅需修 YOLOv5/MNIST 两条"执行期回填"措辞；README 死链与版本号不一致应在打包前顺手清理。**个人研究用途直接分发可行；若面向商业分发，先补 NOTICE 与条款提醒。**

—— 审计证据：requirements.txt、pyproject.toml、README.md、make_dist.py(FRIEND_GUIDE)、paper_repro_app/paper_claims.json、weather_fx.py、day_night.py、ssh_utils.py、database.py、config_store.py、logging_config.py、logger_utils.py、storage_utils.py、remote_runner.py、dataset_discovery.py、repo_crawler.py、app.py、start_app.py/.bat、docs/troubleshoot/GUIDE.md、docs/day_night_research.md、scripts/e2e_task.py、tests/test_basic.py（抽样）。
