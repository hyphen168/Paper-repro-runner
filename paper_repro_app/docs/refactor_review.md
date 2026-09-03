# 复审记录（专家组 verify）

> 复审发现 P0（迁移引入）：
> storage_utils._run_pipeline_in_background 引用 DATA_DB_PATH（未定义，模块仅有 DB_PATH）
> → 线程静默 NameError 死亡，任务卡 running —— pytest 覆盖不到。

## 主管处置（已修复并验证）
- storage_utils.py:32 改 TaskStore(DB_PATH) ✓
- 清理 app.py 未用 import（socket/shlex/threading/timedelta/re）✓
- 删除 0 字节杂散文件 _m ✓
- 修复后：pytest 68 passed；AppTest 0 异常、3 Tabs 正常 ✓

## 其它 P2（登记）
- pyproject [project.scripts] 指向不存在模块（分发走 make_dist，登记后续修）。
- 状态徽章文本含既有 emoji（HTML 生成器外，基线口径）。
