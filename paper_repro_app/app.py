import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

try:
    from tkinter import Tk
    from tkinter.filedialog import askdirectory
except Exception:  # pragma: no cover - GUI may not be available in headless environments
    Tk = None
    askdirectory = None

from paper_repro_app.config_store import LocalConfigStore
from paper_repro_app.database import TaskStore
from paper_repro_app.day_night import ambient_vars, css_vars_block, now_day_night_vars
from paper_repro_app.diagnostics import EnvironmentDiagnostics
from paper_repro_app.log_analyzer import LogAnalyzer
from paper_repro_app.logging_config import DEFAULT_LOG_FILE, get_logger
from paper_repro_app.paper_parser import extract_repo_url
from paper_repro_app.remote_runner import RemoteRunner, inject_public_key, parse_ssh_candidates
from paper_repro_app.ssh_utils import (ensure_default_ssh_keypair, ensure_ssh_key_file,
                                       resolve_ssh_profile, test_ssh_connection, write_ssh_profile)
from paper_repro_app.task_utils import (format_log_preview, get_local_ips, get_step_order,
                                        get_status_color, read_log_tail)
from paper_repro_app.storage_utils import (_get_exec_state, cancel_task, detect_remote_workdir,
                                           ensure_local_storage_tree, is_task_running, resolve_repo_url,
                                           start_pipeline_execution)
from paper_repro_app.logger_utils import enrich_log_for_display
from paper_repro_app.paths import DB_PATH, migrate_legacy_data
from paper_repro_app.repo_crawler import AutoRepoDatasetCrawler
from paper_repro_app.ui_theme import APP_CSS, build_carousel_html, build_stepper_html

# —— re-export（兼容性/测试断言：app 模块命名空间保留领域函数引用，单一实现守卫）——
from paper_repro_app.ssh_utils import parse_ssh_config as parse_ssh_config  # noqa: F401
from paper_repro_app.ssh_utils import parse_ssh_target as parse_ssh_target  # noqa: F401
from paper_repro_app.task_utils import estimate_completion as estimate_completion  # noqa: F401

from paper_repro_app.weather_fx import build_particles_html, describe, get_weather

logger = get_logger("paper_repro_app")


# 任务库统一存放在用户家目录（~/.paper_repro_app），应用目录保持纯代码：
# 拷给朋友不含你的任务数据；升级替换文件夹不丢历史。旧数据自动迁移。
DATA_DB_PATH = DB_PATH
_migrated_files = migrate_legacy_data()
if _migrated_files:
    logger.info("已迁移旧版应用目录数据到用户家目录: %s", ", ".join(_migrated_files))

















def open_directory_dialog(default_path: str) -> str:
    base_dir = default_path or str(Path.home() / "paper_repro_data")
    if Tk is None or askdirectory is None:
        return base_dir
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = askdirectory(initialdir=base_dir, title="选择本地存储目录")
    root.destroy()
    return selected or base_dir





def render_particle_background() -> None:
    """天气粒子背景：默认跟随当地实时天气；侧边栏可切预览覆盖。"""
    try:
        weather = get_weather()
    except Exception:
        weather = None
    info = describe(weather)
    # 昼夜同源：优先用昼夜系统的实时太阳判定（含天气-城市时区），避免天气缓存 30 分钟滞后
    _dn_day = st.session_state.get("dn_day")
    if _dn_day is not None:
        info["is_day"] = bool(_dn_day)
    preview = st.session_state.get("wx_preview", "auto")
    if preview and preview != "auto":
        # 预览覆盖：映射为 (kind, is_day)
        info["kind"], info["is_day"] = preview.split(":") if ":" in preview else (preview, True)
    # 新版 Streamlit: st.iframe 替代已弃用的 st.components.v1.html
    if hasattr(st, "iframe"):
        st.iframe(build_particles_html(weather, override=(info["kind"], info["is_day"])), height=1)
    else:
        components.html(build_particles_html(weather, override=(info["kind"], info["is_day"])), height=0, scrolling=False)


def render_repro_progress(task: dict | None) -> None:
    steps = get_step_order()
    current = (task or {}).get("current_step") or "prepare"
    current_idx = steps.index(current) if current in steps else 0
    progress = min(100, max(4, int(((current_idx + 1) / len(steps)) * 100)))
    status_value = str((task or {}).get("status", "queued")).lower()
    status_labels = {
        "queued": "待开始",
        "running": "执行中",
        "success": "已完成",
        "failed": "失败",
        "cancelled": "已结束",
        "unknown": "待配置",
    }
    panel_html = (
        "<div class='panel' style='padding: 0.85rem 1rem; margin-top: 1rem;'>"
        "<div class='panel-title'>复现流程</div>"
        + build_stepper_html(
            current,
            status=status_value,
            progress=progress,
            status_label=status_labels.get(status_value, "待开始"),
        )
        + "</div>"
    )
    st.markdown(panel_html, unsafe_allow_html=True)




def render_task_telemetry(task: dict | None, local_structure: dict[str, str] | None = None, logs: str = "") -> None:
    if not task:
        return
    summary = local_structure or {}
    status = str(task.get("status", "queued")).lower()
    current_step = task.get("current_step") or "prepare"
    log_preview = format_log_preview(logs or task.get("log") or "暂无日志")
    metrics = [
        ("任务状态", status or "queued"),
        ("当前阶段", current_step),
        ("云端主机", task.get("host") or "未配置"),
        ("远程目录", task.get("remote_workdir") or "未配置"),
    ]
    metric_html = "".join(
        f"<div class='telemetry-metric'><span class='telemetry-label'>{label}</span><strong>{value}</strong></div>" for label, value in metrics
    )
    local_paths = "".join(
        f"<li><span>{name}</span><code>{path}</code></li>" for name, path in summary.items() if path
    ) or "<li>未生成本地目录</li>"
    st.markdown(
        f"""
        <div class='panel' style='padding: 1rem; margin-top: 1rem;'>
            <div class='panel-title'>云端训练监控</div>
            <div class='telemetry-grid'>{metric_html}</div>
            <div class='telemetry-subpanel'>
                <div class='mini-title'>本地目录结构</div>
                <ul class='directory-list'>{local_paths}</ul>
            </div>
            <div class='telemetry-subpanel'>
                <div class='mini-title'>实时日志</div>
                <pre class='telemetry-log'>{log_preview}</pre>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_task_state(task_id: str, status: str, current_step: str, message: str) -> None:
    store = TaskStore(DATA_DB_PATH)
    store.update_task_status(task_id, status, message, current_step=current_step)
    st.session_state["task_log_preview"] = (message or "")[:4000]
    render_repro_progress({"status": status, "current_step": current_step})




def render_pipeline_steps(task: dict, store: TaskStore) -> None:
    """复现流水线区：完整命令默认折叠不堆积；默认展示“实时滚动播放”面板
    （状态徽章 + 步骤进度 + 日志滚动窗口，每 2 秒自动刷新）。"""
    steps = RemoteRunner(task).build_pipeline()
    st.subheader("复现流水线")

    @st.fragment(run_every=2.0)
    def live_monitor() -> None:
        state = _get_exec_state()
        thread = state.get("thread")
        active_id = state.get("task_id")
        running = bool(thread is not None and thread.is_alive() and active_id == task.get("id"))
        current = store.get_task(task["id"]) if task.get("id") else None
        status = str((current or {}).get("status") or ("running" if running else "idle")).lower()
        label_map = {
            "queued": "排队中", "running": "运行中", "success": "已完成",
            "failed": "执行失败", "cancelled": "已结束",
            "idle": "等待任务开始", "unknown": "状态未知",
        }
        label = label_map.get(status, label_map["unknown"])
        color = get_status_color(status)  # 状态色单源
        if running:
            started_at = state.get("started_at")
            elapsed = int((datetime.now() - started_at).total_seconds()) if started_at else 0
            label = f"运行中 · 已执行 {elapsed // 60} 分 {elapsed % 60} 秒"
        dot = ("<span class='live-dot'></span>" if status == "running"
               else f"<span class='status-dot' style='background: {color};'></span>")
        st.markdown(
            f"<div style='border: 1px solid rgba(0, 240, 255, 0.25); border-radius: 12px; padding: 0.6rem 0.9rem; "
            f"margin-bottom: 0.6rem; background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(9,13,26,0.55));"
            f"backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);'>"
            f"<span style='color: {color}; font-weight: 800; letter-spacing: 0.05em;'>{dot}{label}</span>"
            f"<span style='color: var(--muted); font-size: 0.78rem; margin-left: 0.8rem;'>当前步骤："
            f"<span style='color: var(--amber);'>{(current or {}).get('current_step') or 'prepare'}</span></span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if current:
            render_repro_progress({"status": status, "current_step": current.get("current_step") or "prepare"})
        log_window = ""
        if current and current.get("log"):
            lines = [line.strip() for line in str(current["log"]).splitlines() if line.strip()]
            log_window = "\n".join(lines[-22:])
        if not log_window:
            log_window = read_log_tail(22) or "等待任务开始..."
        st.markdown(
            f"<div class='panel' style='padding: 0.9rem;'>"
            f"<div class='panel-title'>复现流水线 · 实时滚动播放（每 2 秒自动刷新，仅保留最新窗口不堆积）</div>"
            f"<pre class='telemetry-log' style='max-height: 320px;'>{log_window}</pre>"
            f"</div>",
            unsafe_allow_html=True,
        )

    live_monitor()
    with st.expander(f"查看完整流水线命令（共 {len(steps)} 步，默认折叠避免页面堆积）", expanded=False):
        for idx, step in enumerate(steps, start=1):
            st.markdown(f"### {idx}. {step['title']}")
            st.code(step["command"])


def _dn_sample_with_weather(prev=None) -> dict:
    """氛围采样：昼夜 × 天气 → 全套主题 token（玻璃/描边/霓虹/文字/背景 12+ 维度联动）。"""
    vars_now = now_day_night_vars(prev=prev)
    try:
        kind = describe(get_weather()).get("kind") or ""
    except Exception:
        kind = ""
    return ambient_vars(vars_now, kind)


def _dn_persist(vars_now: dict) -> None:
    st.session_state["dn_prev"] = vars_now.get("day_factor")
    st.session_state["dn_day"] = 1 if vars_now.get("sun_a", 0) > 0.5 else 0


@st.fragment(run_every=60.0)
def _day_night_tick() -> None:
    """每 60 秒按本地太阳位置刷新昼夜 CSS 变量（天空/卡片/辉光随真实时间变化）。"""
    prev = st.session_state.get("dn_prev")
    try:
        vars_now = _dn_sample_with_weather(prev=prev)
    except Exception:
        vars_now = None
    if vars_now:
        _dn_persist(vars_now)
        st.markdown(css_vars_block(vars_now), unsafe_allow_html=True)
    # 异常/无结果：静默保留上一组注入值（防闪回深宵默认）


# ================= 微调训练参数面板 =================
_TUNE_KEYS = ["t_framework", "t_batch", "t_epochs", "t_imgsz", "t_weights", "t_device", "t_extra"]


def _tune_defaults() -> None:
    ss = st.session_state
    defaults = {
        "t_framework": "yolov5",
        "t_batch": 16,
        "t_epochs": 50,
        "t_imgsz": 640,
        "t_weights": "",
        "t_device": "0",
        "t_extra": "",
    }
    for k, v in defaults.items():
        ss.setdefault(k, v)


def _build_tune_args() -> str:
    """按当前面板参数生成命令尾缀（框架决定参数风格，空值跳过）。"""
    ss = st.session_state
    fw = str(ss.get("t_framework", "yolov5"))
    parts: list[str] = []
    batch = int(ss.get("t_batch") or 0)
    epochs = int(ss.get("t_epochs") or 0)
    imgsz = int(ss.get("t_imgsz") or 0)
    weights = str(ss.get("t_weights") or "").strip()
    device = str(ss.get("t_device") or "").strip()
    if fw == "ultralytics":
        if batch > 0: parts.append(f"batch={batch}")
        if epochs > 0: parts.append(f"epochs={epochs}")
        if imgsz > 0: parts.append(f"imgsz={imgsz}")
        if weights: parts.append(f"weights={weights}")
        if device: parts.append(f"device={device}")
    else:  # yolov5 风格（也是多数 torch 训练脚本常用）
        if batch > 0: parts.append(f"--batch-size {batch}")
        if epochs > 0: parts.append(f"--epochs {epochs}")
        if imgsz > 0: parts.append(f"--imgsz {imgsz}")
        if weights: parts.append(f"--weights {weights}")
        if device: parts.append(f"--device {device}")
    extra = str(ss.get("t_extra") or "").strip()
    if extra:
        parts.append(extra)
    return " ".join(parts)


def _tune_render_panel() -> None:
    """渲染微调参数面板（控件值持久在 session_state，改参数即 rerun 刷新预览）。"""
    _tune_defaults()
    st.markdown("###### 微调参数（修改后实时预览下方命令）")
    tf1, tf2, tf3 = st.columns([1.4, 1, 1])
    with tf1:
        st.selectbox("训练框架参数风格", ["yolov5", "ultralytics"], key="t_framework",
                     help="yolov5 风格（--batch-size）；ultralytics 风格（batch=）。其它脚本可留空下方参数、只用“附加参数”。")
    with tf2:
        st.number_input("训练批次 batch", min_value=1, max_value=512, key="t_batch")
    with tf3:
        st.number_input("轮数 epochs", min_value=1, max_value=2000, key="t_epochs")
    tf4, tf5, tf6 = st.columns(3)
    with tf4:
        st.selectbox("图像尺寸 imgsz", [320, 416, 512, 640, 768, 1280], key="t_imgsz")
    with tf5:
        st.text_input("设备 device", key="t_device", help="如 0、0,1 或 cpu")
    with tf6:
        st.text_input("预训练权重 / 模型配置", key="t_weights",
                      placeholder="如 yolov5s.pt 或 models/yolov5s.yaml（留空=随机初始化）")
    st.text_input("附加参数（原样追加到命令末尾，如 --lr0 0.001 --cos-lr）", key="t_extra")

    tail = _build_tune_args()
    entry = "python train.py --data \"${PAPER_REPRO_DATA_CONFIG}\""
    st.code((entry + (" " + tail if tail else "")), language="bash")
    st.caption("将自动识别仓库训练入口并把上述参数追加到训练命令；不填任何参数则按仓库默认训练。")


def _tune_collect() -> None:
    """提交时收集面板参数为命令尾缀字符串。"""
    st.session_state["tune_args"] = _build_tune_args()


@st.fragment(run_every=2.0)
def _auto_refresh_monitor(task_id: str) -> None:
    """任务执行中：每 2 秒自动刷新监控区，日志/步进器实时滚动。"""
    _render_monitor_content(task_id)
    t = TaskStore(DATA_DB_PATH).get_task(task_id)
    if str((t or {}).get("status", "")).lower() not in {"queued", "running"}:
        st.rerun(scope="app")


def _render_monitor_content(task_id: str) -> None:
    store = TaskStore(DATA_DB_PATH)
    current_task = store.get_task(task_id)
    if not current_task:
        st.info("任务记录不存在或已被清理。")
    else:
        ensure_local_storage_tree(
            os.path.expanduser(current_task.get("local_data_dir") or str(Path.home() / "paper_repro_data")),
            task_id,
        )
        status = str(current_task.get("status", "unknown")).lower()
        _exec = _get_exec_state()
        _thread = _exec.get("thread")
        _thread_alive = bool(_thread is not None and _thread.is_alive() and _exec.get("task_id") == task_id)
        if status in {"queued", "running"} and not _thread_alive:
            st.warning("该任务标记为执行中，但后台线程已不在运行（应用可能重启过）。可点击下方「重新执行流水线」恢复。")

        # —— 失败定位：从结果 JSON 里取失败步骤，避免步进器退回第一步（“卡住”假象） ——
        result_payload = {}
        try:
            result_payload = json.loads(current_task.get("log") or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        failed_step = str(result_payload.get("failed_step") or "") or (current_task.get("current_step") or "")
        monitor_step = failed_step if failed_step in get_step_order() else (current_task.get("current_step") or "prepare")

        # —— 融合监控卡：步进器 + 关键参数 + 单一日志滚动窗口 ——
        st.markdown(
            (
                "<div class='panel' style='padding: 0.9rem 1rem;'>"
                "<div class='panel-title'>复现流程监控</div>"
                + build_stepper_html(
                    monitor_step,
                    status=status,
                    progress=min(100, max(4, int((((get_step_order().index(monitor_step) if monitor_step in get_step_order() else 0) + 1) / len(get_step_order())) * 100))),
                    status_label={
                        "queued": "待开始",
                        "running": "执行中",
                        "success": "已完成",
                        "failed": "失败",
                        "cancelled": "已结束",
                        "unknown": "待配置",
                    }.get(status, "待开始"),
                )
                + f"<div class='fx-stepper-meta'>"
                f"<span class='meta-pill'>云端 <b>{current_task.get('host') or '未配置'}</b></span>"
                f"<span class='meta-pill'>仓库 <b>{(current_task.get('repo_url') or '').rsplit('/', 1)[-1][:32]}</b></span>"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        preview_log = format_log_preview(current_task.get("log"), max_entries=14) or read_log_tail(14)
        st.markdown(
            (
                "<div class='panel' style='padding: 0.9rem 1rem; margin-top: 0.9rem;'>"
                "<div class='panel-title'>实时执行日志（滚动窗口）</div>"
                f"<pre class='telemetry-log' style='max-height: 340px;'>{preview_log}</pre>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        # —— 结束状态：成功才展示报告；失败只给诊断 ——
        if status in {"success", "failed", "cancelled"}:
            payload = {}
            try:
                payload = json.loads(current_task.get("log") or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {"message": str(current_task.get("log") or "")[:4000]}
            result = payload or {}

            if status == "success":
                analysis = result.get("analysis") or {}
                report = result.get("report") or {}
                comparison_table = result.get("comparison_table") or ""
                project_summary = result.get("project_summary") or ""

                # —— 训练指标卡：有指标直接展示；未训练（降级/安全模式）明确提示 ——
                metrics = result.get("metrics") or {}
                ds = result.get("dataset") or {}
                if metrics:
                    st.markdown("#### 训练指标")
                    prefer_order = ["map", "precision", "recall", "f1", "accuracy", "loss"]
                    keys = sorted(metrics.keys(), key=lambda k: next((i for i, t in enumerate(prefer_order) if t in k.lower()), 99))
                    cols = st.columns(min(4, len(keys)))
                    for idx, key in enumerate(keys):
                        with cols[idx % len(cols)]:
                            st.metric(key.strip(), f"{metrics[key]:.6g}" if isinstance(metrics[key], (int, float)) else str(metrics[key]))
                elif ds.get("degraded"):
                    st.warning("本次任务**未执行训练**：仓库无匹配数据集配置（已自动降级为安全检查）。")
                    st.caption("需要训练请在「提交任务」→ 高级选项中填写数据集 YAML（如 data/coco128.yaml）或改用自定义/微调模式。")
                else:
                    st.info("本次为安全检查模式，未执行训练，故无训练指标。")

                with st.expander("复现结果报告", expanded=True):
                    if report.get("report_path"):
                        st.success(f"复现报告已生成：{report['report_path']}")
                    st.markdown("#### 创新点分析")
                    st.metric("分析置信度", f"{analysis.get('confidence', 0):.2f}")
                    st.write(analysis.get("summary") or "")
                    for item in analysis.get("possible_innovations") or []:
                        st.markdown(f"- {item}")
                    if analysis.get("risks"):
                        st.markdown("**主要风险**")
                        for item in analysis["risks"]:
                            st.markdown(f"- {item}")
                    st.markdown("#### 指标对比")
                    st.markdown(comparison_table or "（暂无实验对比数据）")
                if result.get("dataset"):
                    with st.expander("自动发现的数据集", expanded=True):
                        st.json(result["dataset"])
                with st.expander("GitHub-ready 项目总结", expanded=False):
                    st.code(project_summary or "（暂无）")
            elif status == "failed":
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
                    )
            else:
                st.warning(f"任务已结束（状态：{status}）。")
            with st.expander("查看完整执行结果 (JSON)", expanded=False):
                st.json(result if isinstance(result, dict) else {"raw": str(result)[:4000]})
        # 执行中（queued/running）：有实时滚动日志面板 + 步进器即可，不再叠加提示
        if st.button("结束当前任务", key=f"cancel_{task_id}"):
            store.update_task_status(task_id, "cancelled", "正在中止任务：已通知后台中断云端执行...", current_step="cancelled")
            cancel_task(task_id)
            st.warning("任务已请求中止：后台线程已中断并断开云端连接。")

        if st.button("重新执行流水线", key=f"run_{task_id}"):
            _mem_pwd = _get_exec_state().get("task_passwords", {}).get(task_id, "")
            if not _mem_pwd:
                # 密码只存活于进程内存（重启/换会话即丢失）：现场补输后重执行
                st.session_state[f"rerun_need_pwd_{task_id}"] = True
                st.warning("该任务提交时的密码仅保存在本进程内存（安全策略），当前已不可用。请补输云服务器密码后重试；后台线程随本窗口存活，勿关闭控制台。")
            else:
                started, run_msg = start_pipeline_execution(task_id)
                if started:
                    st.session_state["task_log_preview"] = "流水线已在后台重新启动。"
                    st.rerun()
                else:
                    st.warning(run_msg)
        if st.session_state.get(f"rerun_need_pwd_{task_id}"):
            _pwd_col, _go_col = st.columns([3, 1])
            with _pwd_col:
                _rerun_pwd = st.text_input("云服务器密码（重执行使用，仅内存）", type="password", key=f"rerun_pwd_{task_id}")
            with _go_col:
                if st.button("带密码重执行", key=f"rerun_go_{task_id}", use_container_width=True):
                    started, run_msg = start_pipeline_execution(task_id, password=_rerun_pwd)
                    if started:
                        st.session_state.pop(f"rerun_need_pwd_{task_id}", None)
                        st.session_state["task_log_preview"] = "流水线已带密码重新启动。"
                        st.rerun()
                    else:
                        st.warning(run_msg)

def render_app() -> None:
    st.set_page_config(page_title="论文复现助手", layout="wide")
    st.markdown(
        APP_CSS,
        unsafe_allow_html=True,
    )

    # 首帧立即注入昼夜 CSS 变量（后续每 60s 由 _day_night_tick 刷新）
    if "dn_boot" not in st.session_state:
        st.session_state["dn_boot"] = True
        try:
            _vars0 = _dn_sample_with_weather()
            _dn_persist(_vars0)
            st.markdown(css_vars_block(_vars0), unsafe_allow_html=True)
        except Exception:
            pass
    else:
        _day_night_tick()

    # store 供头部状态胶囊与后续共用（提前实例化，避免胶囊空转）
    store = TaskStore(DATA_DB_PATH)
    weather_info = describe(get_weather())
    weather_chip = ""
    if weather_info.get("temp") is not None:
        city_part = f" · {weather_info['city']}" if weather_info.get("city") else ""
        weather_chip = (
            f"<div class='weather-chip'><span class='dot-mark'></span>"
            f"{weather_info['label']} {weather_info['temp']:.0f}°C{city_part}</div>"
        )
    # 运行状态胶囊（整页级数据，随页面 rerun 刷新；不挂 2s 轮询）
    try:
        _latest = store.list_tasks(limit=1)
        _st0 = str((_latest[0].get("status", "idle") if _latest else "idle")).lower()
        _sc = get_status_color(_st0)
        _pill = (
            f"<div class='pr-pill'><span class='status-dot' style='background: {_sc}; box-shadow: 0 0 8px {_sc};'></span>"
            f"<span style='color: {_sc};'>最近任务 · {_st0}</span></div>"
        )
    except Exception:
        _pill = ""
    rise = "rise-in" if st.session_state.get("dn_rise_done") is None else ""
    st.session_state["dn_rise_done"] = True
    # 顶格拼接（行首零缩进）：避免 markdown 把缩进 HTML 行解析成代码块
    header_lines = [
        "<div class='fresh-header'>",
        f"<div class='brand-zone {rise}'>",
        "<div class='fresh-kicker'>Paper Repro Runner<span class='kb-cursor'></span></div>",
        "<h1 style='margin:0.15rem 0;font-size:clamp(1.9rem,3.5vw,2.6rem);'>论文复现助手</h1>",
        "<div class='fresh-sub'>本地轻量控制端 · 云端计算执行器</div>",
        "</div>",
        "<div class='header-cluster'>",
        _pill,
        weather_chip,
        "</div>",
        "</div>",
    ]
    st.markdown(chr(10).join(header_lines), unsafe_allow_html=True)

    st.markdown(build_carousel_html(), unsafe_allow_html=True)

    st.caption("SYS://PAPER-REPRO-RUNNER // LOCAL-CONTROL // CLOUD-EXEC // NET-OK")

    # 背景粒子流最后渲染：iframe 占位不干扰顶部头部
    render_particle_background()

    config_store = LocalConfigStore()
    saved = config_store.load()

    with st.sidebar:
        st.markdown("### 云端配置")
        st.caption("本地保留任务与日志，云端只负责代码执行与实验重跑。推荐：SSH 私钥 + 自有云服务器。")
        st.caption(f"用户配置目录：{config_store.config_dir}")
        ips = get_local_ips()
        if len(ips) > 1:
            st.caption("局域网地址：" + " / ".join(f"http://{ip}:8505" for ip in ips if ip != "127.0.0.1"))
        else:
            st.caption("本机访问：http://127.0.0.1:8505")
        if "task_id" in st.session_state:
            st.info(f"当前任务：{st.session_state['task_id']}")

        st.markdown("---")
        st.markdown("##### 当地定位与天气")
        from paper_repro_app.weather_fx import (
            WEATHER_PREVIEWS, clear_manual_city, get_manual_city, set_manual_city,
        )
        _manual_city = get_manual_city()
        if _manual_city:
            st.caption(f"当地：{_manual_city}（手动设定，天气与昼夜均按此）")
        _city_input = st.text_input(
            "所在城市（天气/昼夜/明暗氛围按此计算；留空则 IP 自动）",
            value=_manual_city or "",
            placeholder="例如：上海 / 杭州 / 广州 / Chengdu",
            key="city_input",
            label_visibility="collapsed",
        )
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("设为当地", key="city_save", use_container_width=True):
                _ok, _msg = set_manual_city(_city_input)
                if _ok:
                    st.session_state["wx_preview"] = "auto"
                    st.rerun()
                else:
                    st.warning(_msg)
        with _c2:
            if st.button("IP 自动", key="city_auto", use_container_width=True):
                clear_manual_city()
                st.session_state["wx_preview"] = "auto"
                st.rerun()

        st.markdown("##### 背景天气预览")
        from paper_repro_app.weather_fx import WEATHER_PREVIEWS
        _wx_opts = list(WEATHER_PREVIEWS.keys())
        _wx_default = st.session_state.get("wx_preview", "auto")
        if _wx_default not in _wx_opts:
            _wx_default = "auto"
        st.selectbox(
            "天气氛围（默认自动跟随当地天气，可手动预览）",
            _wx_opts,
            index=_wx_opts.index(_wx_default),
            format_func=lambda k: WEATHER_PREVIEWS[k][2],
            key="wx_preview",
            label_visibility="collapsed",
        )

    storage_state_key = "selected_local_data_dir"
    storage_default = st.session_state.get(storage_state_key) or saved.get("local_data_dir", str(Path.home() / "paper_repro_data"))
    if storage_state_key not in st.session_state:
        st.session_state[storage_state_key] = storage_default

    tab_submit, tab_monitor, tab_history = st.tabs(["提交任务", "任务监控", "历史记录"])
    with tab_submit:
        with st.expander("本地输出目录（可选，默认使用用户目录）", expanded=False):
            storage_col, action_col = st.columns([5, 1.6])
            with storage_col:
                local_data_dir = st.text_input(
                    "本地存储目录",
                    key="local_data_dir_input",
                    value=st.session_state.get(storage_state_key, storage_default),
                    label_visibility="collapsed",
                )
                st.session_state[storage_state_key] = local_data_dir
            with action_col:
                if st.button("选择目录", key="choose_local_storage", use_container_width=True):
                    selected = open_directory_dialog(st.session_state.get(storage_state_key, storage_default))
                    if selected:
                        st.session_state[storage_state_key] = selected
                        st.rerun()

        # ============ 卡片 1：论文与云端（必填） ============
        with st.container(border=True):
            st.markdown("##### 论文与代码仓库")
            paper_url = st.text_input("论文链接", value=saved.get("paper_url", "https://arxiv.org/abs/2401.00001"))
            repo_hint = st.text_input("代码仓库候选（可选，留空则从论文页面自动识别）", value=saved.get("repo_hint", ""))
            st.markdown("##### 云服务器（SSH）")
            c1, c2, c3, c4 = st.columns([3, 1, 1.4, 1.6])
            with c1:
                cloud_host = st.text_input(
    "服务器地址 / IP（可多行填写多台候选，自动选用可达者）",
    value=saved.get("cloud_host", "") or "",
    help="AutoDL 等实例每次开机地址可能变化：可一次粘贴多台（每行一条），也支持完整 ssh 命令如 ssh -p 38662 root@connect.xxx.seetacloud.com。提交任务时自动探测并选用第一台可达的机器。",
)
            with c2:
                ssh_port = st.text_input("端口", value=str(saved.get("ssh_port") or "22"))
            with c3:
                cloud_user = st.text_input("用户名", value=saved.get("cloud_user", "") or "root")
            with c4:
                cloud_password = st.text_input("密码（留空则用 SSH 私钥）", value="", type="password")
            ssh_target = st.text_input(
                "SSH 连接串（可选：填 user@host 或 ssh 命令会自动解析，覆盖上方字段）",
                value=saved.get("ssh_target", ""),
                placeholder="root@123.45.67.89 -p 22",
            )
            ssh_meta = resolve_ssh_profile(ssh_target, saved.get("cloud_host", ""), saved.get("cloud_user", ""), saved.get("ssh_key_path", ""))
            if ssh_target.strip() and ssh_meta:
                st.caption("已自动识别：" + ", ".join(f"{key}={value}" for key, value in ssh_meta.items()) + "（可修改上方字段覆盖）")
            # 连接健康条（检测按钮结果；提交前可选参考，不强制）
            _health = st.session_state.get("ssh_health")
            if _health:
                _h_ok = bool(_health.get("ok"))
                st.markdown(
                    f"<div class='ssh-health {'ok' if _h_ok else 'fail'}'><span class='status-dot' "
                    f"style='background: {'#00ffa3' if _h_ok else '#ff2b4a'};'></span>"
                    f"{'连接就绪：' if _h_ok else '连接失败：'}{_health.get('msg', '')}</div>",
                    unsafe_allow_html=True,
                )

            default_cloud_host = ssh_meta.get("host") or saved.get("cloud_host") or cloud_host.strip() or "my-server.example.com"
            default_cloud_user = ssh_meta.get("user") or saved.get("cloud_user") or cloud_user.strip() or "root"
            default_ssh_alias = saved.get("ssh_alias", "papercloud")

        # ============ 卡片 2：运行方式 ============
        with st.container(border=True):
            st.markdown("##### 运行方式")
            run_mode = st.radio(
                "运行方式",
                options=["safe", "auto", "run", "tune"],
                format_func=lambda x: {
                    "safe": "安全检查（不训练，验证环境与代码）",
                    "auto": "自动训练（系统识别仓库训练入口）",
                    "run": "自定义命令（手动填写训练/推理命令）",
                    "tune": "微调训练（参数面板一键生成命令）",
                }[x],
                index=0,
                horizontal=True,
                label_visibility="collapsed",
            )

            if run_mode == "run":
                run_command = st.text_area(
                    "训练或推理命令",
                    value="",
                    placeholder="例如：python train.py --data data/coco128.yaml --epochs 50",
                    help="将原样在云端仓库目录执行；可使用 ${PAPER_REPRO_DATA_CONFIG} 引用自动准备的数据集 YAML 路径。",
                )
            else:
                run_command = ""

            if run_mode == "tune":
                _tune_render_panel()

        # ============ 卡片 3：微调参数面板（tune 模式） ============
        st.markdown("---")
        submitted = st.button("提交复现任务", type="primary", use_container_width=True)

        # ---------- 微调/高级参数处理 ----------
        if run_mode == "tune":
            _tune_collect()
        tune_args = str(st.session_state.get("tune_args", "")) if run_mode == "tune" else ""

        # ============ 高级选项（折叠） ============
        with st.expander("高级选项：仓库加速 / 依赖源 / 数据集 / 超时", expanded=False):
            saved_clone_url = saved.get("clone_url", "")
            if "your-username" in saved_clone_url:
                saved_clone_url = ""
            clone_url = st.text_input("加速仓库地址（可选）", value=saved_clone_url, placeholder="留空使用官方仓库")
            pip_index_url = st.text_input("Python 依赖源（可选）", value=saved.get("pip_index_url", ""), placeholder="留空自动选择最快镜像")
            repo_probe_dir = st.text_input("本地仓库校验目录（可选）", value=saved.get("repo_probe_dir", ""))
            remote_workdir = st.text_input("远程工作目录", value=saved.get("remote_workdir", "") or detect_remote_workdir(repo_hint or paper_url, cloud_user, cloud_host))
            env_mode = st.selectbox("运行环境方式", ["conda", "venv", "docker"], index=0)
            data_config = st.text_input("数据集（YAML 路径 或 ZIP/TAR 直链）", value="", placeholder="如 data/coco128.yaml 或 https://.../dataset.zip", help="支持：① 云端仓库内的 YAML 相对路径；② http(s) 数据包直链——自动下载、解压并生成训练配置（YOLO 格式 images/ 与 labels/ 同级；无 val 目录时自动复用 train）。留空则由系统自动发现。")

            split_enable = st.checkbox(
                "自动划分训练 / 验证 / 测试集（数据集未预划分时生效）",
                value=st.session_state.get("split_enable", False),
                help="按比例随机划分并自动生成配置；划分使用软链接，不复制大文件，训练命令自动指向划分后的数据。",
            )
            if split_enable:
                st.session_state["split_enable"] = True
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    st.number_input("训练 %", min_value=0, max_value=100, value=int(st.session_state.get("split_train", 70)), key="split_train")
                with sc2:
                    st.number_input("验证 %", min_value=0, max_value=100, value=int(st.session_state.get("split_val", 20)), key="split_val")
                with sc3:
                    st.number_input("测试 %", min_value=0, max_value=100, value=int(st.session_state.get("split_test", 10)), key="split_test")
                split_sum = int(st.session_state.get("split_train", 70)) + int(st.session_state.get("split_val", 20)) + int(st.session_state.get("split_test", 10))
                if split_sum == 100:
                    st.caption("比例合计 100%，已就绪。")
                else:
                    st.caption(f"比例合计 **{split_sum}%**，需调整为 100% 后才能提交。")
            else:
                st.session_state["split_enable"] = False
            auto_download_dataset = st.checkbox("自动下载缺失的数据集（完整则复用）", value=True)
            command_timeout = st.number_input("单步执行超时（分钟）", min_value=1, max_value=1440, value=int(saved.get("command_timeout", 60)))

        # ============ SSH 密钥与诊断（折叠） ============
        with st.expander("SSH 私钥 / 免密登录 / 连接诊断", expanded=False):
            try:
                generated_ssh_key, generated_ssh_public_key = ensure_default_ssh_keypair()
            except RuntimeError as exc:
                generated_ssh_key, generated_ssh_public_key = "", ""
                st.error(str(exc))
            saved_ssh_key = saved.get("ssh_key_path", "")
            default_ssh_key = ssh_meta.get("key") or ensure_ssh_key_file(saved_ssh_key) or generated_ssh_key or "~/.ssh/id_ed25519"
            ssh_key_path = st.text_input("SSH 私钥路径（或粘贴私钥全文）", value=default_ssh_key)
            ssh_alias = st.text_input("SSH 配置别名", value=saved.get("ssh_alias", "papercloud"))
            if generated_ssh_public_key:
                st.caption("免密公钥（追加到云端 /root/.ssh/authorized_keys 后即可免密登录，需用时复制）：")
                st.code(generated_ssh_public_key, language="text")
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                gen_profile_btn = st.button("生成 SSH 配置", use_container_width=True, key="gen_ssh_profile")
            with bc2:
                test_conn_btn = st.button("测试 SSH 连接", use_container_width=True, key="test_ssh_conn")
            with bc3:
                inject_key_btn = st.button("注入公钥到服务器", use_container_width=True, key="inject_pub_key")
            if gen_profile_btn:
                profile_path = write_ssh_profile(
                    ssh_alias.strip() or "papercloud",
                    cloud_host.strip() or default_cloud_host,
                    cloud_user.strip() or default_cloud_user,
                    ssh_port.strip() or "22",
                    ssh_key_path.strip() or default_ssh_key,
                )
                st.success(f"SSH 配置已写入 {profile_path}，可执行 ssh {ssh_alias.strip() or 'papercloud'}")
            if test_conn_btn:
                ok, msg = test_ssh_connection(
                    host=(cloud_host or default_cloud_host).strip(),
                    user=(cloud_user or default_cloud_user).strip(),
                    port=ssh_port.strip() or "22",
                    key=ssh_key_path.strip() or default_ssh_key,
                    password=cloud_password,
                    alias=(ssh_alias or default_ssh_alias).strip() or "papercloud",
                )
                st.session_state["ssh_health"] = {"ok": bool(ok), "msg": msg}
                st.rerun()
            if inject_key_btn:
                ok, msg = inject_public_key(
                    host=(cloud_host or default_cloud_host).strip(),
                    user=(cloud_user or default_cloud_user).strip(),
                    port=ssh_port.strip() or "22",
                    key=ssh_key_path.strip() or default_ssh_key,
                    password=cloud_password,
                    public_key=generated_ssh_public_key,
                )
                st.success(msg) if ok else st.error(msg)
        if submitted:
            auto_run = run_mode in {"auto", "tune"}
            selected_run_command = run_command.strip() if run_mode == "run" else ""
            if run_mode == "run" and not selected_run_command:
                st.error("请填写目标仓库的训练、验证或推理命令；不同论文的参数不能安全地自动假设。")
                st.stop()

            data_split = ""
            if split_enable:
                _s_tr = int(st.session_state.get("split_train", 70))
                _s_va = int(st.session_state.get("split_val", 20))
                _s_te = int(st.session_state.get("split_test", 10))
                if _s_tr + _s_va + _s_te != 100:
                    st.error(f"数据集划分比例合计需为 100%（当前 {_s_tr + _s_va + _s_te}%）。")
                    st.stop()
                data_split = f"{_s_tr},{_s_va},{_s_te}"
            # Automated crawler engine to evaluate and rank optimal repository and dataset
            crawler = AutoRepoDatasetCrawler()
            crawl_results = crawler.evaluate_and_rank_candidates(paper_url, repo_hint)
            best_candidate = crawl_results.get("best_candidate")

            detected_repo = extract_repo_url(paper_url)
            repo_url = (best_candidate.get("repo_url") if best_candidate else None) or resolve_repo_url(repo_hint, detected_repo)

            effective_clone_url = clone_url.strip() or (best_candidate.get("accelerated_url") if best_candidate else None) or (best_candidate.get("clone_url") if best_candidate else None) or repo_url

            if not repo_url:
                st.error("未识别到可用的论文代码仓库。请在“代码仓库候选”中填写真实 Git 仓库地址后重新提交。")
                st.stop()

            st.toast(f"已定位代码仓库：{repo_url}")

            ssh_target_value = ssh_target.strip()
            resolved_profile = resolve_ssh_profile(ssh_target_value, cloud_host.strip(), cloud_user.strip(), ssh_key_path.strip())
            resolved_cloud_host = resolved_profile.get("host") or cloud_host.strip() or "my-server.example.com"
            resolved_cloud_user = resolved_profile.get("user") or cloud_user.strip() or "root"
            resolved_ssh_key = resolved_profile.get("key") or ssh_key_path.strip() or "~/.ssh/id_rsa"
            resolved_ssh_port = ssh_port.strip() or resolved_profile.get("port") or "22"

            # ---- 自动识别候选机：目标串优先 + 主机框多行/多台 ----
            import re as _re
            cand_lines = [ssh_target_value] if ssh_target_value else []
            for _ln in _re.split(r"[\n;,]+", cloud_host.strip()):
                _ln = _ln.strip()
                if _ln and _ln != resolved_cloud_host:
                    cand_lines.append(_ln)
            if cand_lines:
                host_candidates = parse_ssh_candidates(
                    cand_lines,
                    default_user=(cloud_user.strip() or "root"),
                    default_port=int(resolved_ssh_port or 22),
                )
                if host_candidates:
                    resolved_cloud_host = host_candidates[0]["host"]
                    resolved_cloud_user = host_candidates[0]["user"] or resolved_cloud_user
                    resolved_ssh_port = str(host_candidates[0]["port"])
            else:
                host_candidates = []
            if len(host_candidates) > 1:
                st.caption(f"已登记 {len(host_candidates)} 台候选机器，提交后自动探测并选用可达者执行。")
            if not cloud_password.strip() and not ensure_ssh_key_file(resolved_ssh_key):
                st.error("SSH 凭据无效，任务已阻止提交：填写的“SSH 私钥路径”不是可用的私钥文件，且未提供云服务器密码，后台将无法连接云服务器。")
                st.caption("排查建议：① 私钥路径应为真实私钥文件或粘贴私钥全文；② 填写云服务器密码；③ 确认端口为实例实际开放的 SSH 端口；④ 可先在上方“SSH 私钥/免密登录”区点击“测试 SSH 连接”验证凭据。")
                st.stop()
            resolved_remote_dir = remote_workdir.strip() or detect_remote_workdir(repo_hint or paper_url, resolved_cloud_user, resolved_cloud_host)
            resolved_local_dir = (st.session_state.get("selected_local_data_dir") or local_data_dir or str(Path.home() / "paper_repro_data")).strip()

            active_tasks = [task for task in store.list_tasks(limit=20) if task.get("status") in {"queued", "running"}]
            if active_tasks:
                st.warning("检测到已有未结束任务，系统将自动中止旧任务并直接开始新任务。")
                for active_task in active_tasks:
                    store.update_task_status(active_task["id"], "cancelled", "已被更高优先级任务替换，正在中止旧任务。", current_step="cancelled")
                    cancel_task(active_task["id"], wait_seconds=6.0)
                # 等待旧线程完全退出，避免新任务无执行者
                import time as _time
                for _ in range(10):
                    if not any(is_task_running(t["id"]) for t in active_tasks):
                        break
                    _time.sleep(0.5)

            config_store.save(
                {
                    "pip_index_url": pip_index_url.strip(),
                    "ssh_target": ssh_target_value,
                    "cloud_host": (cloud_host.strip() if cloud_host.strip() else resolved_cloud_host),
                    "cloud_user": resolved_cloud_user,
                    "ssh_key_path": resolved_ssh_key,
                    "ssh_port": resolved_ssh_port,
                    "ssh_alias": ssh_alias.strip() or "papercloud",
                    "local_data_dir": resolved_local_dir,
                    "repo_probe_dir": repo_probe_dir,
                    "env_mode": env_mode,
                    "command_timeout": int(command_timeout),
                    "remote_workdir": resolved_remote_dir,
                }
            )

            probe_dir = Path(repo_probe_dir).expanduser() if repo_probe_dir.strip() else None
            if probe_dir and probe_dir.exists():
                diagnosis = EnvironmentDiagnostics(probe_dir).diagnose()
                with st.expander("自动环境诊断结果", expanded=True):
                    st.json(diagnosis)

            if repo_hint.strip():
                st.toast("已使用用户提供的代码仓库候选值继续执行。")
            elif not detected_repo:
                st.warning("未从论文页面中自动识别到代码仓库，请先填写仓库候选值。")

            task = store.create_task(
                paper_url=paper_url,
                repo_url=repo_url,
                host=resolved_cloud_host,
                user=resolved_cloud_user,
                ssh_key_path=os.path.expanduser(resolved_ssh_key),
                port=resolved_ssh_port,
                clone_url=effective_clone_url or repo_url,
                pip_index_url=pip_index_url.strip(),
                remote_workdir=resolved_remote_dir,
                local_data_dir=os.path.expanduser(resolved_local_dir),
                environment_mode=env_mode,
                run_command=selected_run_command,
                command_timeout=int(command_timeout) * 60,
                data_config=data_config.strip() if (selected_run_command or auto_run) else "",
                model_weights="",
                auto_download_dataset=auto_download_dataset if (selected_run_command or auto_run) else False,
                auto_run=auto_run,
                tune_args=tune_args,
                data_split=data_split,
                status="queued",
                current_step="prepare",
            )
            task["password"] = cloud_password

            st.session_state["task_id"] = task["id"]
            st.session_state["task_log_preview"] = "任务已创建，等待云端执行开始..."
            ensure_local_storage_tree(resolved_local_dir, task["id"])
            run_mode_label = {"safe": "安全检查", "auto": "自动训练", "run": "自定义命令", "tune": "微调训练"}.get(run_mode, run_mode)
            extra = " · 已应用微调参数" if tune_args else ""
            st.toast(f"任务已创建 {task['id']} · {run_mode_label}{extra} · 前往「任务监控」查看实时进度")

            runner = RemoteRunner(task)
            runner.build_pipeline()
            st.session_state["task_log_preview"] = "任务已提交，后台流水线已启动，监控页每 2 秒自动刷新实时进度。"

            store.update_task_status(task["id"], "running", "任务已进入云端执行阶段，准备按流水线执行复现步骤。", current_step="prepare")
            started, startup_msg = start_pipeline_execution(
                task["id"], password=cloud_password, hosts=host_candidates or None,
            )
            if not started:
                st.error(f"新任务未能启动：{startup_msg}。旧任务可能仍在结束中，请稍候在「任务监控」点击重新执行。")
            st.rerun()


    with tab_monitor:
        current_task_id = st.session_state.get("task_id")
        if not current_task_id:
            st.info("暂无进行中的任务。前往「提交任务」创建新复现任务。")
        else:
            current_task = store.get_task(current_task_id)
            if not current_task:
                st.info("任务记录不存在或已被清理。")
            else:
                task_status = str(current_task.get("status", "unknown")).lower()
                if task_status in {"queued", "running"}:
                    _auto_refresh_monitor(current_task_id)
                else:
                    _render_monitor_content(current_task_id)

    with tab_history:
        log_analyzer = LogAnalyzer()
        tasks_list = store.list_tasks(limit=12)
        if not tasks_list:
            st.info("还没有任务记录。前往「提交任务」创建你的第一个复现任务。")

        for task in tasks_list:
            status = str(task.get("status", "unknown")).lower()
            status_color = get_status_color(status)
            status_label = {
                "queued": "待开始",
                "running": "执行中",
                "success": "已完成",
                "failed": "失败",
                "cancelled": "已结束",
                "unknown": "未知",
            }.get(status, status)
            repo_short = (task.get("repo_url") or "未填写仓库").rsplit("/", 1)[-1][:46]
            st.markdown(
                (
                    "<div class='panel-row' style='padding: 0.7rem 0.9rem; margin: 0.45rem 0;'>"
                    f"<div style='display: flex; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap; align-items: center;'>"
                    f"<div><span class='status-dot' style='background: {status_color};'></span>"
                    f"<b style='color: var(--text-strong);'>{task['id']}</b>"
                    f"<span style='color: var(--muted); font-size: 0.78rem; margin-left: 0.55rem;'>{status_label}</span>"
                    f"<span style='color: var(--muted); font-size: 0.72rem; margin-left: 0.55rem;'>当前: {task.get('current_step', 'queued')}</span></div>"
                    f"<span style='color: var(--muted); font-size: 0.72rem;'>{repo_short}</span>"
                    f"</div></div>"
                ),
                unsafe_allow_html=True,
            )
            if status in {"failed", "error"}:
                diag = log_analyzer.analyze_log(task.get("log"))
                with st.expander(f"错误诊断 [{task['id']}] 错误定位与根因诊断", expanded=False):
                    st.error(f"错误类别: {diag['error_category']} | 触发步骤: {diag['failed_step']}")
                    st.markdown("**关键报错日志片段:**")
                    st.code(diag["error_snippet"], language="text")
                    st.markdown(f"**根因分析:** {diag['cause']}")
                    st.markdown(f"**推荐解决方案:** {diag['suggestion']}")

        with st.expander("查看后台系统日志文件 (app.log)", expanded=False):
            if DEFAULT_LOG_FILE.exists():
                log_text = enrich_log_for_display(DEFAULT_LOG_FILE.read_text(encoding="utf-8", errors="replace"))
                st.code("\n".join(log_text.splitlines()[-40:]), language="text")
                st.caption(f"日志存储路径: {DEFAULT_LOG_FILE}")
            else:
                st.info("尚无后台系统日志输出。")

if __name__ == "__main__":
    render_app()
