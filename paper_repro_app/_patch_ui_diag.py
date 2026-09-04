# -*- coding: utf-8 -*-
"""批2：失败诊断卡（E_* 三段式）+ 侧栏 FAQ（排障规范最小落地）"""
from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')


def rep(old, new, tag):
    global s
    assert old in s, '未找到: ' + tag
    s = s.replace(old, new, 1)


# 1) 失败映射表 + 渲染函数（放在 _render_success_result 前）
fn = '''
# —— 失败映射：关键词 -> (错误码, 结论, 动作, 手册锚点)（排障规范 v1.0 三段式）——
_FAILURE_MAP = [
    (("CUDA", "cuda", "Torch not compiled"), "E_TORCH_CPU",
     "云端环境的 PyTorch 是 CPU 版或缺失，无法用 GPU 训练。",
     "重新执行任务即可自动重装 CUDA 版（国内源优先，已禁止 CPU 回退）。仍失败请检查云端网络。", "G-3.3"),
    (("ModuleNotFoundError", "No module named"), "E_DEP_SWALLOW",
     "运行期缺少 Python 包（依赖安装阶段曾被容忍跳过）。",
     "重新执行任务（本次依赖失败将直接中断并列出缺包）。", "G-3.4"),
    (("认证失败", "Authentication", "Authentication failed", "凭据", "authorized_keys"), "E_CONN_AUTH",
     "云端拒绝了当前登录凭据（密码或密钥不匹配）。",
     "核对密码；或在本页「注入公钥到服务器」；AutoDL 密码在实例控制台重置后重试。", "G-2.4"),
    (("均无法连接", "无法连接", "Unable to connect", "refused", "Connection refused", "timed out", "超时"), "E_CONN_UNREACH",
     "无法连接到云服务器（实例可能关机、地址已变或网络不通）。",
     "打开实例控制台确认开机，整行复制最新 SSH 登录指令粘贴到服务器地址框（可多填几台自动选用可达者）。", "G-2.1"),
    (("数据集", "degraded", "未找到含"), "E_DS_DEGRADE",
     "数据集准备失败：仓库无匹配配置或下载不可用。",
     "在「高级选项 → 数据集」填 YAML 相对路径或 ZIP/TAR 直链后重试；或改用自定义命令并在命令内自行准备数据。", "G-5.1"),
    (("入口", "识别", "entrypoint", "ModelNotFound"), "E_MODEL_ENTRY",
     "未能自动识别该仓库的训练入口（脚本命名不常见或在子目录）。",
     "切到「实际运行」模式，粘贴仓库 README 中的训练命令；也可参考日志中的候选脚本列表。", "G-4.2"),
    (("超过", "超时", "TimeoutError", "timed out"), "E_RUN_TIMEOUT",
     "某个步骤执行超时（可能网络慢或训练卡住）。",
     "在高级选项中调大单步超时后重试；若训练本身卡死请先结束任务。", "G-4.3"),
    (("out of memory", "OutOfMemory", "显存", "CUDA out of memory"), "E_GPU_RES",
     "GPU 显存不足或驱动不匹配。",
     "调小 batch / 输入尺寸 / 使用更小模型后重试。", "G-4.4"),
]


def _classify_failure(message: str):
    text = (message or "")
    for keywords, code, conclusion, action, anchor in _FAILURE_MAP:
        if any(kw.lower() in text.lower() for kw in keywords):
            return code, conclusion, action, anchor
    return "", "任务执行失败。", "查看下方技术详情；仍无法解决可在任务详情复制诊断摘要寻求帮助。", "G-0"


def _render_failure_card(task_id: str, message: str, diag: dict, raw_result: str = "") -> None:
    code, conclusion, action, anchor = _classify_failure(message)
    st.error(f"任务执行失败" + (f"（{code}）" if code else "") + "：" + conclusion)
    st.caption("建议操作：" + action)
    with st.expander("技术详情与诊断", expanded=True):
        if diag.get("error_category") or diag.get("failed_step"):
            st.markdown(f"**错误类别**: {diag.get('error_category')} | **触发步骤**: {diag.get('failed_step')}")
        if diag.get("error_snippet"):
            st.code(str(diag.get("error_snippet"))[:2000], language="text")
        if diag.get("cause"):
            st.markdown(f"**根因分析**: {diag.get('cause')}")
        if diag.get("suggestion"):
            st.markdown(f"**推荐方案**: {diag.get('suggestion')}")
        if message and message != str(diag.get("error_snippet") or ""):
            st.markdown("**原始错误**:")
            st.code(str(message)[:1500], language="text")
    st.caption("手册条目：" + anchor + "（docs/troubleshoot/GUIDE.md）")
    diag_text = (
        f"任务 {task_id}\\n错误码 {code or '未知'}\\n结论：{conclusion}\\n建议：{action}\\n"
        f"详情：{(diag.get('cause') or message or '')[:800]}"
    )
    st.button("复制诊断摘要", key=f"diag_copy_{task_id}",
              help="复制后可直接粘贴给朋友或 AI 助手寻求帮助。")
    st.session_state[f"diag_text_{task_id}"] = diag_text


def _render_success_result(result: dict, task_meta: str = "") -> None:'''
rep("def _render_success_result(result: dict, task_meta: str = \"\") -> None:", fn, 'failure-map')

# 2) 监控 failed 分支：三段式诊断卡（保留 LogAnalyzer 详情）
old_fail = '''            elif status == "failed":
                fail_message = (result.get("message") or str(current_task.get("log") or ""))[:3000]
                st.error(f"任务执行失败：{fail_message}")
                log_analyzer = LogAnalyzer()
                diag = log_analyzer.analyze_log(json.dumps(result, ensure_ascii=False) or fail_message)
                with st.expander("错误定位与根因诊断", expanded=True):
                    st.error(f"错误类别: {diag['error_category']} | 触发步骤: {diag['failed_step']}")
                    st.markdown("**关键报错日志片段:**")
                    st.code(diag["error_snippet"], language="text")
                    st.markdown(f"**根因分析:** {diag['cause']}")
                    st.markdown(f"**推荐解决方案:** {diag['suggestion']}")
                if any(
                    keyword in fail_message
                    for keyword in ("认证", "Authentication", "Authentication failed", "凭据", "authorized_keys")
                ):
                    st.caption(
                        "SSH 认证类错误排查：1) 点击「注入公钥到服务器」；2) 私钥路径应为真实私钥文件或粘贴私钥全文；"
                        "3) 本机公钥需已加入云服务器 ~/.ssh/authorized_keys；"
                        "4) 确认端口为实例实际开放的 SSH 端口（AutoDL 通常 4xxxx）；5) 或改用密码认证。"
                    )'''
new_fail = '''            elif status == "failed":
                fail_message = (result.get("message") or str(current_task.get("log") or ""))[:3000]
                log_analyzer = LogAnalyzer()
                diag = log_analyzer.analyze_log(json.dumps(result, ensure_ascii=False) or fail_message)
                _render_failure_card(
                    str(current_task.get("id") or "task"),
                    fail_message,
                    diag,
                    raw_result=json.dumps(result, ensure_ascii=False)[:4000],
                )'''
rep(old_fail, new_fail, 'monitor-fail')

p.write_text(s, encoding='utf-8')
print('批2 诊断卡注入（1/2）')
