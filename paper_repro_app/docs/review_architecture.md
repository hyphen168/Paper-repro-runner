# 架构与可维护性评审（专家组 B · reviewer 输出汇总）

> 主管汇总落盘；逐文件核对 app.py 1477 行、remote_runner 998 行、包 25 模块、tests 60 用例。

## 健康处
- 依赖方向健康：仅 app.py import streamlit；领域/基础/分析/UI-builder 均可独立单测。
- 落盘执行已成体系；线程异常兜底完整；可移植性由测试固化。

## 主要发现
- F1(P1) remote_runner.detect_ssh_auth_sources 完全重复定义两处（:122 与 :626）→ 已由实施去重（P0-2）。
- F2(P1) “结束任务”仅改 DB 标签，无法真正中止线程/远端；提交自动中止旧任务同样不停线程；线程管理收口建议 TaskExecutor（带 Lock/Event）。
- F3(P1) 执行 10 步 vs 展示 8 步漂移（model/run 缺失），run/model 阶段步进器退回第 1 步；状态映射 5 处重复。
- F4 建议：app.py 纯逻辑按 ssh_utils/task_utils/storage_utils 外迁（已实施，app.py 939 行）；views/ 拆分为后续。
