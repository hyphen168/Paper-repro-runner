# 交付评估与封装规范 v2.0（主导裁决版）

三份报告已通读并交叉核对（a_pkg 打包审计 / b_gap 交付阻断 / c_legal 合规）。冲突裁决与修订注记：b 报告 P0-B"档案自动回写未接线"的核查时点早于父会话批 4 提交（repo_profiles 接线 + 92 测试全绿已入库），故降级为复核项而非重做；b 报告 P0-A 与 paper_switch 规范批 5（入口识别扩展/候选确认流）未落地相印证，采纳其"入口失败自助闭环"最小交集并修正文案承诺；a 与 c 均指出打包清单收窄与版本统一，合并为单一 P0。本规范为发布实施唯一依据，冲突处以本文为准。

## 一、交付评估结论

**附条件可交付。** 依据：三份报告在"无真实凭据/私钥/密钥材料会进包、密码零落盘零落包、依赖许可面无阻断、92 测试全绿、核心链路（连接引擎/环境自举/CUDA 保障/数据集引擎/指标兜底/对比表/排障/档案记忆）证据充分"上一致；条件为本次必须落地的 8 项 P0（预计约 0.5-1 个工作日）与 1 项发布前真机冒烟（P1-9，本机无法复现全新安装路径，属残余风险，须在朋友机或干净 Windows 上执行一次）。泄漏与合规维度已确认干净；打包清单经收窄后无内部痕迹。不满足条件不发布；满足后按 v2.0.0 发版即可交付给非专家用户。

## 二、P0 修复清单（8 项，本次必须全部落地）

### P0-1 打包清单收窄与卫生（make_dist.py）
- 改动：排除集新增 `.ruff_cache`；剔除根级 `_*.py`、`scripts/`、`tests/`、`create_desktop_shortcut.py`；docs 除 `docs/troubleshoot/` 外全部剔除（仅留 GUIDE.md）；`requirements.txt` 的 `pytest==9.1.1` 注释化（dev-only）。
- 验收：zip 内 grep "BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY"、"connect.cqa1"、"47754" 零命中；无 scripts/tests/_*.py/.ruff_cache；仅含 docs/troubleshoot。

### P0-2 启动失败可见化（start_app.py + start_app.bat）
- 改动：`streamlit run` 的 `subprocess.run(check=False)` 改为捕获 returncode，非 0 打印中文失败原因（含退出码与求助提示）并 `sys.exit(rc)`；bat 保留 errorlevel 检查与 pause。
- 验收：构造一次启动崩溃（临时改坏 app.py）→ 窗口不闪退、显示中文错误与退出码；还原后正常。

### P0-3 启动顺序与默认监听（start_app.py）
- 改动：先 Popen 起服务，轮询 127.0.0.1 端口就绪（≤20s）再开浏览器；`--server.address` 默认改 127.0.0.1（回环免防火墙弹窗）。
- 验收：清 pyc 冷启动后浏览器打开即服务可用；netstat 显示仅回环监听。

### P0-4 版本统一与旧件清理
- 改动：make_dist VERSION、pyproject version、`paper_repro_app/__init__` __version__ 三处统一升 2.0.0；FRIEND_GUIDE 内版本一致；旧件 `PaperReproRunner-1.5.0.zip` 及同名说明移入 `archive/1.5.0/`。
- 验收：三处 grep 均 2.0.0；zip 名 PaperReproRunner-2.0.0.zip；旧件已归档。

### P0-5 入口失败自助闭环（最小交集，不实现候选确认 UI 全量）
- 改动：run 步骤入口失败（退出码 65 / 含"识别并启动模型"）时，失败诊断卡 E_MODEL_ENTRY 建议升级为按钮「复制仓库与命令到提交页修改」：写 session（repo_url + 档案上次 run_command 或空）跳转提交页预填「实际运行」模式供编辑重跑。同步改 GUIDE G-4.2 措辞（删除"识别扩展会自动给出候选清单供确认"承诺，改为"未自动识别时按提示粘贴仓库 README 训练命令"）。
- 验收：人造入口失败 → 诊断卡出现跳转入口 → 提交页带出仓库与命令可编辑。

### P0-6 对比表措辞与文档清理（paper_claims.json + README）
- 改动：YOLOv5 0.287 与 MNIST 99.0 两处 source 中"commit 执行期回填"改为"官方教程/README 基线（随包快照 v2.0.0）"；README §8 死链清理（改为 GUIDE.md 相对路径），目录树去除真实账号类叙述。
- 验收：claims 无"执行期回填"字样；README 链接逐一存在。

### P0-7 合规文件与隐私小节（新增 LICENSE / NOTICE.txt / 说明段落）
- 改动：根目录新增 LICENSE（MIT）与 NOTICE.txt（依赖清单含 paramiko LGPL-2.1 说明 + 外部服务署名与用途）；FRIEND_GUIDE 与 README 加「网络与隐私」小节（见第五节终稿）。
- 验收：LICENSE/NOTICE 入包；说明含隐私段；无密码明文。

### P0-8 复制诊断摘要去伪（app.py 失败卡）
- 改动：诊断摘要渲染为可见 st.code 块（可全选复制）+ toast 提示"摘要已生成，选中上方文本复制"，移除"点击即复制"的死承诺。
- 验收：失败卡片有可见摘要与提示文案，无点了无反应按钮。

## 三、P1 建议清单（可后置）

1. 档案回写复核（b P0-B 降级）：grep upsert_profile( 调用点确认已接线；空态文案改为"成功跑过的仓库会自动记忆"。
2. LAN 显式开关：侧栏"允许局域网访问"复选框 + 重启提示。
3. 端口文案动态化：硬编码 8505 展示文案改为读实际端口。
4. docs 研究性报告归档保留仓库、不入包（P0-1 已保证）。
5. UI 补一句数据集许可提示（GUIDE 已有）。
6. 真机 clean-room 冒烟（发布前必做）：干净 Windows 上验收单第 3 步。
7. FRIEND_GUIDE 增"升级"节（删旧解新；数据在 ~/.paper_repro_app 保留迁移）。

## 四、发布配置终版

- 版本号 2.0.0（特性跨度大：天气/昼夜、SSH 自动连接引擎、数据集引擎、排障体系、档案记忆均新增，符合主版本语义）。
- zip 名 PaperReproRunner-2.0.0.zip；顶层说明 PaperReproRunner-2.0.0-使用说明.txt（含本版新增 + 网络与隐私 + 升级节）。
- 变更说明模板：v2.0.0 新增：实时天气与昼夜明暗主题；SSH 自动连接（多候选自动选用可达者、连接串/别名/密钥三形态解析）；多论文自适应（换论文粘贴链接即可；同仓库二次提交自动预填上次成功配置）；复现结果与论文对比表可见（指标卡、结果说明、证据日志）；自助排障（失败诊断卡 E_* 码、侧栏速查、完整手册）；数据集增强（URL 直链自动解压与 YOLO 配置生成、非 YOLO 数据根目录导出、仓库自管数据标记）；云端健壮性（CUDA torch 自动重装、依赖多源与预算、验证容错分级、指标 stdout 兜底）。
- 包内清单（裁定）：start_app.bat/py、requirements.txt（pytest 注释化）、README.md、LICENSE、NOTICE.txt、使用说明 txt、.streamlit/config.toml、paper_repro_app/、docs/troubleshoot/GUIDE.md。
- 剔除：scripts/、tests/、docs/ 其余研究报告、根级 _*.py、.ruff_cache、create_desktop_shortcut.py、assets/、data/logs/.venv。
- 保留安全：.streamlit 仅主题色；用户数据 ~/.paper_repro_app 不入包。

## 五、合规声明终版（可直接写入 FRIEND_GUIDE/README）

「网络与隐私：本工具为本地单机应用，无账号、无遥测、无后台回传。运行时会请求以下第三方服务完成定位与加速：ip-api.com（以公网 IP 换粗粒度城市定位，免费档非商用）、Open-Meteo（天气与地理编码）、GitHub/Gitee/arXiv（论文与仓库检索）、清华/阿里等 pip 镜像（测速择优）、download.pytorch.org（CUDA 版 PyTorch）、ghfast.top 与清华 Miniconda（GitHub 与安装包加速）——其中云端下载均在您自己的云服务器上发起。凭据安全：云服务器密码只保存在本机进程内存，重启即失效，不落盘、不进日志、不入安装包；粘贴私钥保存在本机 ~/.ssh/ 下 0600 权限文件；日志输出已脱敏。提醒：数据集直链 URL 若携带签名 token 会随下载日志明文显示，请使用短期签名链接。许可：本工具以 MIT 协议发布；依赖库均宽松许可，其中 paramiko 为 LGPL-2.1（经 pip 安装，不构成二进制再分发）；天气数据与昼夜算法来自 Open-Meteo 与 NOAA 公开模型；公开数据集请核对各自原始许可。本工具仅供研究与学习用途；复现指标与论文数值的对比口径见任务报告级别注记，不构成对论文结论的替代验证。」

## 六、交付验收单（实施=父进程）

| 步骤 | 判据 | 负责 |
|---|---|---|
| 1 打包 | make_dist 产出 2.0.0 zip；清单符合第四节；P0-1 泄漏扫描零命中 | 父进程 |
| 2 副本冒烟 | 解压至新目录；删 .venv 重建；AppTest 0 异常；启动 8505 curl 200；P0-2/3 验证通过 | 父进程 |
| 3 三项演练 | a 陌生人旅程（引导→配置服务器→成功任务→结果/对比可见）；b 失败路径（错误凭据→E_* 诊断卡→摘要可见→按建议重跑成功）；c 换论文（新仓库成功→档案生成→二次提交预填可一键填入） | 父进程（发布前干净 Windows 补跑 P1-9） |
| 4 数据迁移 | 旧 ~/.paper_repro_app 数据启动 2.0.0 副本：历史/档案/配置仍在，DB 迁移幂等 | 父进程 |
| 5 终检 | 92+ 测试全绿、AppTest 0 异常；zip 与说明无密码明文/真实域名；git 无临时脚本 | 父进程 |
