"""P0 fixes validation: env step fallback + dependencies heredoc check."""
from __future__ import annotations


from paper_repro_app.remote_runner import RemoteRunner


def _build_steps(env_mode: str = "venv", task_overrides: dict | None = None):
    task = {"id": "test-p0", "host": "h", "user": "u",
            "environment_mode": env_mode, "auto_run": False}
    if task_overrides:
        task.update(task_overrides)
    return RemoteRunner(task).build_pipeline()


def test_env_step_detects_system_python_not_hardcoded():
    steps = _build_steps("venv")
    env = next(s for s in steps if s["id"] == "env")
    # 必须探测系统 Python，而非硬编码 python3（日志中 exit 127 的根因）
    assert "SYSTEM_PYTHON=$(command -v python3 || command -v python || true)" in env["command"]
    # 最终必须有可读的错误指引，而不是裸 127
    assert "未找到可用的 Python 解释器" in env["command"] or "exit 1" in env["command"]


def test_env_step_has_miniconda_auto_install_fallback():
    steps = _build_steps("venv")
    env = next(s for s in steps if s["id"] == "env")
    # 服务器无 conda 无 python 时自动安装 Miniconda（清华镜像）
    assert "miniconda.sh" in env["command"]
    assert "mirrors.tuna.tsinghua.edu.cn" in env["command"]


def test_env_step_conda_mode_uses_conda_branch():
    steps = _build_steps("conda")
    env = next(s for s in steps if s["id"] == "env")
    assert "conda_activate_paperrepro" in env["command"]


def test_dependencies_step_no_heredoc_truncation():
    """日志中 bash here-doc 截断 (wanted PYnimport) 的根因：heredoc 内联。
    当前实现将脚本落盘 (.dep_scan.py) 后执行，避免 bash 解析截断。"""
    steps = _build_steps("venv", {"auto_run": False})
    dep = next(s for s in steps if s["id"] == "dependencies")
    # 落盘执行：先写 .dep_scan.py 再执行脚本文件
    assert ".dep_scan.py" in dep["command"], "依赖扫描脚本未落盘执行"
    assert "base64.b64decode" in dep["command"]
    # 不应出现裸 <<'PY' heredoc 形式或单行内联 exec 执行
    assert "<<'PY'" not in dep["command"]
    assert "'import base64; exec(base64.b64decode" not in dep["command"]

def test_dependencies_step_disk_script_replayable():
    """落盘脚本应通过日志回放可见（StepLogger.log_command 打印完整命令）。"""
    # 落盘路径写入 repo 目录，且脚本文件名固定便于排查
    steps = _build_steps("venv")
    dep = next(s for s in steps if s["id"] == "dependencies")
    assert "Path('.dep_scan.py').write_text" in dep["command"]
    # conda 分支同样应使用落盘方式
    steps_conda = _build_steps("conda")
    dep_conda = next(s for s in steps_conda if s["id"] == "dependencies")
    assert "Path('.dep_scan.py').write_text" in dep_conda["command"]


def test_pipeline_all_steps_have_command():
    steps = _build_steps("venv")
    for step in steps:
        assert step["command"], f"步骤 {step['id']} 缺少命令"