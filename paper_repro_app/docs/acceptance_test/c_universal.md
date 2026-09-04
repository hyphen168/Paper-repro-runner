## Review 说明

本子代理无写盘工具，按硬约束 1 现将全文报告放本回复，建议父进程落盘为 `docs/acceptance_test/audit_universal_usage.md`。审计基于对代码/文档的实际核查（app.py、start_app.py/bat、make_dist.py、remote_runner.py、storage_utils.py、comparison_table.py、report_generator.py、paths.py、ssh_utils.py、ui_theme.py、requirements.txt、pyproject.toml、README），未做真机执行，密码一律不出现。

---

# 普适性审计报告：任何人拿到都能用吗？

## 结论先行

不能。核心断裂点有三个：论文原文指标没有注入入口（对比表"论文列"恒为占位符）、纯密码机器的恢复/重执行链路在重启后必然失败、数据集自动获取规范未落地导致"任意论文 35 分钟出指标"依赖人工选料。其余为体验与打包问题，均可后置。

## 1) 开箱路径模拟（陌生 Windows 用户，无 conda、无云背景）

最小步数：解压(1) → 装 Python 3.11+(2) → 双击 start_app.bat(3) → 浏览器开 8505(4) → 填论文链接(5) → 填服务器信息(6) → 测试连接(7) → 选运行方式并提交(8) → 等执行(9) → 看指标与报告(10)。每步风险：

1. 解压：zip 带 MOTW，杀软/SmartScreen 可能弹"解除锁定"；说明 txt 在 zip 外（make_dist.py 把使用说明写到 OUT_DIR 而非 zip 内），只发 zip 就丢了说明。
2. 装 Python：README 写"3.10+"、pyproject requires-python>=3.10，但依赖 pandas==3.0.5 实需 3.11+（start_app.py 强制 3.11，口径不一致）；`py -3` 可能选中 3.13/3.14，未验证。
3. bat：较健壮（三路找 python、版本拦截、venv 重建、依赖指纹+镜像回退均具备），风险低。
4. 浏览器先于服务就绪打开（start_app.py 先 open_browser 再 run streamlit），首次可能见"无法访问此网站"，需手动刷新。
5. 论文链接：默认预填样例 arXiv 链接，直接点提交会走联网爬虫后报"未识别仓库"，文案可理解但耗时长。
6. 服务器信息：**最大认知缺口**。端口默认"22"（app.py），AutoDL 实际为随机端口；若用户只粘贴域名不粘贴"登录指令"，必失败。帮助文案有解析能力（支持 `ssh -p x root@connect.xxx` 整行），但用户不知道 AutoDL 控制台哪里复制。
7-10. 执行与产物链路已真机验证（yolov5 safe 全链路 success），风险集中在数据集缺失（degrade-fatal）与训练中断恢复。

## 2) 缺口清单

- **首次引导缺失**：无"新手上路/向导"。侧边栏只说"推荐 SSH 私钥+自有云服务器"，全 app 仅一处 tooltip 提到 AutoDL（app.py:676）。AutoDL 用户需要的"三步"（复制登录指令整行→填实例密码→测试连接）无任何指引；轮播条是纯营销文案（ui_theme.py CAROUSEL_CARDS）。
- **默认值合理性**：端口默认 22 对 AutoDL 必错；用户名 root 合理；密码不落库（仅进程内存）安全但换 session 即失效；服务器地址回退"my-server.example.com"占位，漏填时直到 SSH 失败才暴露。
- **错误文案**：提交前校验、SSH 认证类诊断、数据集 degrade、verify 文案基本可操作；弱点是远程裸 stdout 直出，非技术用户难读。
- **指标对比缺口（证据级）**：storage_utils.py 生成对比表时 `paper:"待填充"`、`gap:"待论文指标"`，report_generator.py 报告无指标表；app 内无任何填写"原文数值+出处"的入口。与"论文对比报告自动生成"的产品声称不符。
- **重执行缺口（证据级）**：密码只存 `_EXEC_STATE` 内存表；app.py 监控页"重新执行流水线"调 `start_pipeline_execution(task_id)` 不带密码，重启/断线程后纯密码机必然认证失败，无重输密码入口。
- **断链防护**：后台线程为 daemon，关控制台窗口即断；远端训练进程无 nohup 保护，可能残留占用 GPU 计费（AutoDL 场景成本风险）。
- **指标覆盖面**：收集脚本只认 results.csv/metrics.csv/results.json/metrics.json 四类文件；只打印 stdout 指标或写其他文件名的仓库"指标都要"不成立。
- **数据集链路**：auto 模式仓库无官方下载配置且无用户直链时 degrade-fatal；dataset_lead_spec（docs/dataset_url_research/）已出未落地，选论文必须自带可下载数据。
- **端口/防火墙**：start_app 以 `0.0.0.0` 绑定，首次运行触发 Windows 防火墙弹窗且应用无鉴权，同网段他人可驱动你的云端机器执行命令；侧边栏端口文案硬编码 8505，与实际 free-port 可能不符。
- **打包**：.streamlit/config.toml、docs、tests 会进包（可用但冗余）；assets/ 被排除（start_app 不依赖，安全）；使用说明未入包顶层；VERSION 1.5.0 与 pyproject 0.2.0 不一致。
- **版本/依赖**：全 `==` 锁版本，但需预检清华/阿里等镜像同步了 pandas 3.0.5、streamlit 1.62.0 等新版本，否则首启安装会在国内网络空转。
- **代码卫生**：app.py 底部遗留死代码 main()（再启 8503 实例），`python app.py` 直跑会因无 streamlit 上下文报错。

## 3) "任何人"分级与最短路径

- **A 级（有云服务器、懂 SSH）**：解压→装 Python→启动→填论文→粘贴 `ssh -p 端口 user@host` 整行→（填密码或用"注入公钥"）→提交。现存链路已通，无需新功能；建议在表单给"粘贴 ssh 命令"高亮样例。
- **B 级（只有 AutoDL 账号）**：需新增一个"AutoDL 三步"折叠引导：① 控制台复制"登录指令"整行粘贴到 SSH 连接串 ② 粘贴实例密码 ③ 点"测试 SSH 连接"后再提交；并自动识别 seetacloud 域时给端口提示。B 级最短路径=3 步表单+1 次提交，属最小改动、最高收益。
- **C 级（无服务器先看效果）**：当前无演示模式，提交必依赖真机。建议后置做"示例任务种子"：历史记录预置一条成功示例（含指标卡、对比表、报告），离线即可看全界面效果。

## 4) 优先级

**P0（验收测试前必做，4 项）**
1. 原文指标注入闭环：加"论文原文指标+出处"可选输入（如高级选项内 JSON/逐行文本），随任务存储并写入对比表与报告，消除恒"待填充"。
2. 密码机恢复链路：任务重新执行时若缺密码则要求现场输入（并提示线程中断原因）；配合"启动窗口勿关"的界面警示，控制 GPU 残留风险。
3. 数据集链路真机最小闭环预检：验收论文一律预置"官方下载配置或用户直链+校验通过"才放行，避免 auto 模式 degrade-fatal 反复打断 30 分钟级任务。
4. 指标可收集性规则：验收论文白名单须满足"仓库产出标准 results 文件"或先给收集脚本加 stdout 指标兜底，否则"指标都要"目标落空。

**P0 附带的两个小修**：使用说明 txt 写进 zip 顶层；README/pyproject 的 Python 版本口径统一为 3.11+。

**可后置项（P1/P2）**：AutoDL 三步引导与表单高亮样例（B 级体验）；防火墙/0.0.0.0 改 127.0.0.1 默认+可选 LAN 开关；启动器改为端口就绪后再开浏览器；杀软/MOTW 说明文案；app.py 死代码清理与端口文案去硬编码；示例任务种子（C 级）；verify 容错与多主机 L1/L2 收尾。