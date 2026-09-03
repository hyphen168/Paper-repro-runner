const ROOT = 'C:/Users/27779/Desktop/industrial-vision-repro/paper_repro_app';
const DOCS = ROOT + '/docs';
const BASE = '基线：pytest 60 passed；代码约 7134 行（app.py ~1970 + 包内 ~25 文件 + tests）；git 仓库。';
const CD = '写文件一律用绝对路径；bash 前先 cd ' + ROOT + '。';

const planTask = [
  '你是专家组领导（Team Lead）。请通读项目代码并制定《专家评审任务书与模块化目标》。',
  '项目：' + ROOT + '（Streamlit 论文复现控制台：app.py 单文件主界面 + paper_repro_app/ 包：remote_runner/database/weather_fx/ui_theme/repo_crawler 等 + tests + docs）。',
  BASE,
  '任务：1) 快速通读 app.py 与包结构（read/grep）；2) 诊断最大问题：app.py 单体过大耦合、后台线程与 Streamlit 生命周期、远程 bash 命令生成的可维护性、UI 与领域逻辑混杂；',
  '3) 给出模块化目标架构（建议新增模块划分、职责边界、依赖方向、公共层），把论文配置/云执行/数据集/UI 展示/主题天气拆开；明确哪些改、哪些不动（保持 pytest 绿 + UI 可运行 + 可打包分发）；',
  '4) 撰写 ' + DOCS + '/review_lead_plan.md（结构：现状诊断/模块化蓝图/分工验收标准/风险与禁忌）。',
  CD,
  '完成后 300 字内返回摘要。'
].join('\n');

const revATask = [
  '你是「代码质量与安全专家」。评审项目 ' + ROOT + '。',
  BASE,
  '重点：1) 异常处理、资源泄漏(SSH/文件/线程)、SQLite 并发、paramiko 正确性、subprocess/远程 shell 拼接注入面；2) 安全：SSH 密钥/密码处理、路径注入、恶意仓库 URL 注入、密钥泄漏风险；3) 明确 bug 与隐患（尽量指出文件与行）。',
  '可运行静态分析：先 cd ' + ROOT + '，尝试 ./.venv/Scripts/python.exe -m pip install ruff -q（失败则跳过），再 ./.venv/Scripts/python.exe -m ruff check app.py paper_repro_app scripts tests --select E,F,B,S --output-format concise；失败不阻塞。',
  '输出：' + DOCS + '/review_quality_security.md（问题分级 P0 必修/P1 应修/P2 建议，含位置+原因+建议）。返回 300 字摘要。'
].join('\n');

const revBTask = [
  '你是「架构与可维护性专家」。评审 ' + ROOT + '。',
  BASE,
  '重点：1) app.py 约 2000 行单体：功能分区、重复代码、全局状态组织；2) 后台线程与 Streamlit rerun/fragment 生命周期耦合风险；3) remote_runner 中巨型 bash/python 字符串拼装的可维护性评估与改进方向（模板化/落盘脚本化已有基础，评估完善度）；4) UI(展示) 与领域逻辑耦合点；',
  '5) 输出「模块化拆分建议清单」：每项含拆到哪个新模块/保留/抽函数、依赖方向、验收方式。',
  '输出：' + DOCS + '/review_architecture.md。返回 300 字摘要。'
].join('\n');

const revCTask = [
  '你是「测试与工程化专家」。评审 ' + ROOT + '。',
  BASE,
  '重点：1) tests/ 质量：覆盖什么、漏什么（远程 runner bash 生成、数据库迁移、UI HTML builder、weather、可移植性）；2) 断言是否脆弱/依赖实现细节；3) 工程化：requirements 锁定、.gitignore、打包产物、docs、本地化 CI 建议；4) 列出应补的高价值测试（优先级+理由）。',
  '先跑 ./.venv/Scripts/python.exe -m pytest tests/ -q --tb=no 确认绿。输出：' + DOCS + '/review_testing.md。返回 300 字摘要。'
].join('\n');

const qaTask = [
  '你是「静态分析与量化专家」（只测量不写业务代码）。项目 ' + ROOT + '。',
  BASE,
  '任务：1) 尝试安装度量工具：cd ' + ROOT + ' && ./.venv/Scripts/python.exe -m pip install ruff radon -q（失败跳过）；ruff check 选 E,F,B 与复杂度；radon cc 找圈复杂度>15 的函数、radon mi 维护性指数；',
  '2) 输出量化表：文件行数/函数数/最长函数/复杂度 top10/重复块提示；3) 列出 app.py 可安全切分函数的候选名单（纯函数优先：不依赖 st.* 与模块级全局），便于后续机械拆分。',
  '输出：' + DOCS + '/review_static_metrics.md。返回 300 字摘要。'
].join('\n');

const plan = await runs.run('lead-plan', { agent: 'oracle', task: planTask });

const reviews = await runs.all([
  { key: 'revA', agent: 'reviewer', task: revATask },
  { key: 'revB', agent: 'reviewer', task: revBTask },
  { key: 'revC', agent: 'reviewer', task: revCTask },
  { key: 'qa', agent: 'worker', task: qaTask },
]);

const decideTask = [
  '你是专家组领导，进入裁决阶段。读取以下文件（位于 ' + DOCS + '/）：',
  'review_lead_plan.md / review_quality_security.md / review_architecture.md / review_testing.md / review_static_metrics.md',
  '任务：1) 交叉核对与去重；2) 裁决模块化重构蓝图定稿：目标结构（模块划分/依赖方向）、分阶段实施步骤（每步文件与预期测试）、P0 修复清单（安全与数据丢失优先，含修法）、本轮立即可做低风险清单 vs 建议后续清单；3) 明确禁止事项（不改业务行为/无 emoji/保持可打包结构/界面功能不变）。',
  '写入定稿：' + DOCS + '/refactor_plan.md。返回 300 字摘要（含阶段列表）。'
].join('\n');

const decide = await runs.run('lead-decide', { agent: 'oracle', task: decideTask });

const implTask = [
  '你是实施工程师，按定稿蓝图执行。先读取 ' + DOCS + '/refactor_plan.md。',
  '项目 ' + ROOT + '；' + BASE,
  '执行要求：1) 严格按蓝图本阶段范围实施（模块化拆分 + P0 修复，低风险优先）；2) 每完成一大步运行 ./.venv/Scripts/python.exe -m pytest tests/ -q 保持全绿（重构需改测试断言须同步并说明）；3) 不改变用户可见业务行为与文案（无 emoji、不重排界面）；4) 蓝图与现实冲突时记录 deviation，取最小侵入方案并说明；5) 不运行 streamlit 长进程。',
  '完成后：pytest 并写实施记录 ' + DOCS + '/refactor_impl_report.md（改动清单/新结构/测试结果/deviation/遗留项）。返回 400 字摘要（含最终 pytest 结果与主要改动）。'
].join('\n');

const impl = await runs.run('lead-impl', { agent: 'worker', task: implTask });

const verifyTask = [
  '你是复审工程师。审查实施结果（项目 ' + ROOT + '，实施记录见 ' + DOCS + '/refactor_impl_report.md）。',
  '任务：1) 跑 pytest 全绿；2) 抽查改动：app.py 是否瘦身/职责迁移符合蓝图；remote_runner/database/ui_theme 是否被意外破坏；3) 检查回归：HTML builder/stepper/carousel/UI class、可移植路径、无 emoji、无硬编码绝对路径（可 grep）；4) 输出 ' + DOCS + '/refactor_review.md：通过/需返工清单。返回 250 字摘要。'
].join('\n');

const finalTask = [
  '你是专家组领导，终审。读取 ' + DOCS + '/refactor_impl_report.md 与 ' + DOCS + '/refactor_review.md（如存在），抽查项目结构。',
  '产出最终质量报告 ' + DOCS + '/code_quality_report.md：1) 总体质量评级(A-E)与依据；2) 本轮成果；3) 遗留问题与后续路线图；4) 给用户的 5 条最重要建议（面向继续开发与维护）。',
  '最后用中文返回完整总结（500 字内）：评级 + 已改什么 + 测试情况 + 后续建议。'
].join('\n');

const finals = await runs.all([
  { key: 'verify', agent: 'reviewer', task: verifyTask },
  { key: 'final', agent: 'oracle', task: finalTask },
]);

return {
  plan: plan.output,
  reviews: reviews.map(function (r) { return { key: r.key, output: r.output }; }),
  decide: decide.output,
  impl: impl.output,
  finals: finals.map(function (r) { return { key: r.key, output: r.output }; }),
};
