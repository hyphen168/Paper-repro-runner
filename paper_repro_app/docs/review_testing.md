# 测试与工程化评审（专家组 C · reviewer 输出汇总）

> 主管汇总落盘。静态核对 60 用例与源码一致。

## 长处
- 远程流水线以“命令生成+bash -n 语法校验”务实分层；e2e_task 真机驱动分离。
- 可移植性测试（硬编码路径/版本锁定/家目录数据/哈希隔离）是真资产。
- UI/天气纯模块单测；P0 事故点固化（test_p0_fixes）。

## 短板
1. 数据库迁移路径（onUpgrade/migrate_legacy_data）零覆盖（实施已补 v6→8 迁移测试）。
2. UI 步进器 8 步 vs 真实 10 步漂移未被测试捕获（列为路线图）。
3. 个别断言依赖实现细节/存在空洞恒真断言；README 主题描述与实现矛盾。
4. 工程化：打包入口配置损坏（scripts 指向不存在模块）、_m 杂散文件（已删）、无 CI。
5. bash 校验在无 bash 环境静默跳过（Windows 注意）。

## 建议补测
- 组合矩阵（venv/conda×auto×data_split×tune）、命令注入 sanitize、build_plan/execute/inject_public_key、落盘脚本执行级验证。
