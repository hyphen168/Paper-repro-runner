import base64
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("streamlit_app_module", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP_MODULE)
parse_ssh_target = APP_MODULE.parse_ssh_target
resolve_repo_url = APP_MODULE.resolve_repo_url
detect_remote_workdir = APP_MODULE.detect_remote_workdir

from paper_repro_app.artifacts import ArtifactCollector
from paper_repro_app.config_store import LocalConfigStore
from paper_repro_app.database import TaskStore
from paper_repro_app.diagnostics import EnvironmentDiagnostics
from paper_repro_app.dataset_discovery import DatasetDiscovery
from paper_repro_app.model_discovery import ModelDiscovery
from paper_repro_app.innovation_analysis import PaperInnovationAnalyzer
from paper_repro_app.project_summary import generate_project_summary
from paper_repro_app.remote_runner import RemoteRunner
from paper_repro_app.report_generator import generate_repro_report
from paper_repro_app.comparison_table import generate_experiment_table


def test_remote_pipeline_steps_are_valid_bash():
    bash_path = shutil.which("bash")
    if bash_path is None or "windowsapps" in Path(bash_path).parts[-2].lower():
        return
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "environment_mode": "venv",
    })
    for step in runner.build_pipeline():
        syntax_check = subprocess.run(
            ["bash", "-n"],
            input=step["command"].encode("utf-8"),
            capture_output=True,
            check=False,
        )
        assert syntax_check.returncode == 0, f"{step['id']}: {syntax_check.stderr.decode('utf-8', errors='replace')}"


def test_task_store_round_trip(tmp_path):
    db_path = tmp_path / "tasks.db"
    store = TaskStore(db_path)
    task = store.create_task(
        id="task-123",
        paper_url="https://arxiv.org/abs/1234.5678",
        repo_url="https://github.com/example/demo",
        host="example.com",
        user="ubuntu",
        ssh_key_path="/tmp/id_rsa",
        remote_workdir="/workspace/demo",
        local_data_dir="/tmp/data",
    )
    assert task["id"] == "task-123"
    assert store.get_task("task-123")["repo_url"] == "https://github.com/example/demo"
    assert store.get_task("task-123")["port"] == "22"

    store.update_task_status("task-123", "running", "start")
    store.append_task_log("task-123", "step 1 done")
    assert "step 1 done" in store.get_task("task-123")["log"]


def test_task_store_persists_remote_ssh_port(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create_task(
        paper_url="https://arxiv.org/abs/2407.02988",
        repo_url="https://github.com/example/demo",
        host="connect.cqa1.seetacloud.com",
        user="root",
        port="12680",
        ssh_key_path="",
        remote_workdir="/root/autodl-tmp/paper-repro",
        local_data_dir=str(tmp_path),
    )
    assert task["port"] == "12680"


def test_extract_repo_url_handles_known_hosts():
    repo_url = "https://github.com/example/repro-project"
    assert repo_url in repo_url
    assert "github.com" in repo_url


def test_explicit_repo_hint_overrides_automatic_repo_detection():
    repo_url = "https://github.com/hyphen168/Yolov5m-NEU-DET.git"
    assert resolve_repo_url(repo_url, "https://huggingface.co/huggingface") == repo_url


def test_app_does_not_expose_article_specific_training_command_builder():
    assert not hasattr(APP_MODULE, "build_yolo_training_command")


def test_generic_huggingface_detection_is_not_used_as_source_code_repo():
    assert resolve_repo_url("", "https://huggingface.co/huggingface") == ""


def test_parse_ssh_target_keeps_port_out_of_host_and_uses_ssh_values():
    parsed = parse_ssh_target("ssh -p 12680 root@connect.cqa1.seetacloud.com -i ~/.ssh/id_rsa")
    assert parsed["host"] == "connect.cqa1.seetacloud.com"
    assert parsed["user"] == "root"
    assert parsed["port"] == "12680"
    assert parsed["key"] == "~/.ssh/id_rsa"


def test_parse_ssh_config_reads_host_port_and_user(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text(
        "Host connect.cqa1.seetacloud.com\n"
        "  HostName connect.cqa1.seetacloud.com\n"
        "  Port 18681\n"
        "  User root\n",
        encoding="utf-8",
    )
    profile = APP_MODULE.parse_ssh_config("connect.cqa1.seetacloud.com")
    assert profile["host"] == "connect.cqa1.seetacloud.com"
    assert profile["port"] == "18681"
    assert profile["user"] == "root"


def test_write_ssh_profile_creates_reusable_alias(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_path = tmp_path / ".ssh" / "config"
    written_path = APP_MODULE.write_ssh_profile(
        "papercloud",
        "connect.cqa1.seetacloud.com",
        "root",
        "12680",
        "~/.ssh/id_ed25519",
        config_path=config_path,
    )
    content = written_path.read_text(encoding="utf-8")
    assert written_path == config_path
    assert "Host papercloud" in content
    assert "HostName connect.cqa1.seetacloud.com" in content
    assert "Port 12680" in content
    assert "User root" in content


def test_ensure_default_ssh_keypair_creates_reusable_key(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    private_key, public_key = APP_MODULE.ensure_default_ssh_keypair()
    assert Path(private_key).is_file()
    assert (tmp_path / ".ssh" / "id_ed25519.pub").is_file()
    assert public_key.startswith("ssh-ed25519 ")


def test_invalid_ssh_key_path_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "ssh_key_path": "rkjrPg4Okyj/",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
    })
    auth = runner.detect_ssh_auth_sources()
    assert auth["resolved_key"] is None
    assert auth["has_any_auth"] in {False, True}


def test_remote_runner_accepts_password_fallback():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "password": "secret123",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "environment_mode": "venv",
    })
    assert runner.password == "secret123"
    assert "password" in runner.execute.__code__.co_names


def test_remote_runner_uses_single_shell_script():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "ssh_key_path": "~/.ssh/id_rsa",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "environment_mode": "venv",
    })
    script = runner.build_shell_script()
    assert "set -euo pipefail" in script
    assert "bash -lc" not in script
    assert ". .venv/bin/activate" in script


def test_remote_runner_uses_shallow_lfs_free_clone():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
    })
    clone_command = runner.build_pipeline()[1]["command"]
    assert "GIT_LFS_SKIP_SMUDGE=1" in clone_command
    assert "--depth 1" in clone_command
    assert "--no-tags" in clone_command
    assert "--progress" in clone_command
    assert "git ls-remote --heads" in clone_command
    assert "http.lowSpeedTime 45" in clone_command
    assert "timeout 13 git ls-remote --heads" in clone_command
    assert "timeout 600 git clone" in clone_command
    assert "ghfast.top" in clone_command or "_try_sources" in clone_command
    # github 直连地址应预置加速后备
    assert "ghfast.top" in clone_command
    assert "自动多源回退" in clone_command


def test_remote_runner_discovers_and_installs_missing_import_dependencies():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
    })
    dependency_command = next(
        step["command"] for step in runner.build_pipeline()
        if step["id"] == "dependencies"
    )
    assert "AUTO_DISCOVERED_PACKAGES" in dependency_command
    assert "基础运行 import" in dependency_command
    # 兼容单/双引号包裹的 base64（落盘执行使用单引号，旧内联方式使用双引号）
    encoded = re.search(r"base64\.b64decode\(['\"]([^'\"]+)['\"]\)", dependency_command).group(1)
    assert "'flask': 'flask'" in base64.b64decode(encoded).decode("utf-8")
    assert '"$PYTHON_BIN" -m pip check' in dependency_command
    assert "继续执行代码验证" in dependency_command
    assert "here-document" not in dependency_command
    # 落盘执行方式：先写 .dep_scan.py，再执行脚本文件（不再使用内联 exec）
    assert '"$PYTHON_BIN" -c "from pathlib import Path' in dependency_command
    assert "Path('.dep_scan.py').write_text" in dependency_command
    assert 'PYTHON_BIN="$PWD/.venv/bin/python"' in dependency_command
    assert '[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$SYSTEM_PYTHON"; ' in dependency_command
    assert "SYSTEM_PYTHON=$(command -v python3 || command -v python || true)" in dependency_command
    assert "else if [ -f .venv/bin/activate ]" not in dependency_command
    assert "[ -f .venv/bin/activate ] && . .venv/bin/activate" in dependency_command


def test_remote_runner_switches_pip_mirror_after_slow_install():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
    })
    install_command = next(
        step["command"] for step in runner.build_pipeline()
        if step["id"] == "install"
    )
    assert "pip_install_with_fallback" in install_command
    assert "PIP_CACHE_DIR" in install_command
    assert "--cache-dir" in install_command
    assert "当前依赖源安装失败或超时，自动切换下一个备用源重试" in install_command
    assert "pypi.tuna.tsinghua.edu.cn" in install_command
    assert "mirrors.aliyun.com" in install_command
    assert "&& pip_install_with_fallback()" not in install_command
    assert "SYSTEM_PYTHON=python3" in install_command
    assert 'PYTHON_BIN="$PWD/.venv/bin/python"' in install_command
    verify_command = next(
        step["command"] for step in runner.build_pipeline()
        if step["id"] == "verify"
    )
    assert "import pytest" in verify_command
    assert "pytest" in verify_command


def test_remote_runner_recovers_from_missing_conda_path_and_scans_datasets():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/root/autodl-tmp/paper-repro",
        "auto_run": True,
    })
    steps = {step["id"]: step["command"] for step in runner.build_pipeline()}
    assert "/root/miniconda3/bin/conda" in steps["env"]
    assert 'export PATH="$(dirname "$CONDA_BIN"):$PATH"' in steps["env"]
    assert "自动回退到 Python venv" in steps["env"]
    assert "自动发现仓库数据集配置" in steps["dataset"]
    assert "PAPER_REPRO_DATASET_JSON" in base64.b64decode(
        re.search(r"base64\.b64decode\(['\"]([^'\"]+)['\"]\)", steps["dataset"]).group(1)
    ).decode("utf-8")
    assert 'eval "$("$CONDA_BIN" shell.bash hook 2>/dev/null || true)"' in steps["verify"]
    assert "PAPER_REPRO_AUTO_RUN_COMMAND" in steps["run"]
    assert "未能自动推断训练命令" in steps["run"]


def test_remote_runner_accepts_explicit_model_run_command():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "run_command": "python train.py --epochs 1",
    })
    run_command = next(step["command"] for step in runner.build_pipeline() if step["id"] == "run")
    assert "准备执行模型运行阶段" in run_command
    assert "python train.py --epochs 1" in run_command


def test_remote_runner_bounds_actual_model_command_and_collects_results():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "run_command": "python train.py --epochs 1",
        "command_timeout": 3600,
    })
    steps = {step["id"]: step["command"] for step in runner.build_pipeline()}
    assert "timeout 3600 bash -c" in steps["run"]
    encoded = re.search(r"base64\.b64decode\(['\"]([^'\"]+)['\"]\)", steps["collect"]).group(1)
    assert "PAPER_REPRO_RESULTS_JSON" in base64.b64decode(encoded).decode("utf-8")
    assert "训练数据配置不存在" not in steps["run"]


def test_remote_runner_checks_configured_training_dataset_before_running():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "run_command": "python train.py --epochs 1",
        "data_config": "data/NEU-DET.yaml",
    })
    run_command = next(step["command"] for step in runner.build_pipeline() if step["id"] == "run")
    assert ".paper_repro_dataset.env" in run_command


def test_remote_runner_downloads_missing_dataset_from_trusted_yaml_instruction():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "data_config": "data/coco128.yaml",
        "auto_download_dataset": True,
        "auto_run": True,
    })
    dataset_command = next(step["command"] for step in runner.build_pipeline() if step["id"] == "dataset")
    encoded = re.search(r"base64\.b64decode\(['\"]([^'\"]+)['\"]\)", dataset_command).group(1)
    script = base64.b64decode(encoded).decode("utf-8")
    assert "数据集缺失，执行仓库 YAML 声明的官方下载来源" in script
    assert "已识别数据集 YAML，但数据集缺失且仓库未声明官方下载指令" in script
    assert "shutil.copyfileobj" in script  # 手动分块下载（支持 308 跟随与重试）
    assert "zipfile.is_zipfile" in script
    assert "下载后未找到 YAML 声明的 train/val 路径" in script
    assert "data/coco128.yaml" in dataset_command


def test_dataset_discovery_is_self_contained_and_exposes_training_config():
    script = DatasetDiscovery.build_remote_script()
    assert "root.rglob('*')" in script
    assert "仓库 README 中发现候选链接" in script
    assert "PAPER_REPRO_DATA_CONFIG" in script
    assert "PAPER_REPRO_DATASET_JSON" in script


def test_dataset_download_helper_injects_context_fallback():
    """仓库下载脚本若引用上下文变量 yaml（如 yaml['path']），须注入兜底：
    独立执行时从声明下载指令的 YAML 配置加载为字典，避免 NameError。"""
    script = DatasetDiscovery.build_remote_script()
    assert "PAPER_REPRO_HELPER_CONFIG" in script
    assert "yaml = _yaml_lib.safe_load(_raw) or {}" in script or "if _raw: yaml" in script
    assert "temp_py.write_text(prelude + download" in script

    payload = {"config_path": "data/custom.yaml", "downloaded": True}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    assert DatasetDiscovery.extract_payload(f"{DatasetDiscovery.result_marker}{encoded}") == payload


def test_remote_runner_uses_discovered_dataset_environment_file():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "run_command": 'python train.py --data "${PAPER_REPRO_DATA_CONFIG}"',
        "auto_download_dataset": True,
    })
    steps = {step["id"]: step["command"] for step in runner.build_pipeline()}
    assert "自动发现仓库数据集配置" in steps["dataset"]
    assert ".paper_repro_dataset.env" in steps["run"]


def test_remote_runner_auto_run_discovers_standard_training_command():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "auto_run": True,
    })
    steps = {step["id"]: step["command"] for step in runner.build_pipeline()}
    assert ModelDiscovery.env_file_name in steps["run"]
    assert "PAPER_REPRO_AUTO_RUN_COMMAND" in steps["run"]
    assert "自动发现仓库数据集配置" in steps["dataset"]


def test_remote_runner_decodes_collected_metrics():
    payload = {"metrics": {"metrics/mAP50(B)": 0.81}, "metric_sources": ["runs/train/results.csv"], "artifacts": ["runs/train/weights/best.pt"]}
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    extracted = RemoteRunner.extract_collection_payload(f"output\nPAPER_REPRO_RESULTS_JSON={encoded}\n")
    assert extracted == payload


def test_task_store_persists_model_execution_settings(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    task = store.create_task(
        paper_url="https://arxiv.org/abs/2407.02988",
        repo_url="https://github.com/example/repro-project",
        host="example.com",
        user="root",
        run_command="python train.py --epochs 1",
        command_timeout=3600,
    )
    assert task["run_command"] == "python train.py --epochs 1"
    assert task["command_timeout"] == 3600


def test_remote_runner_uses_autodl_data_disk_for_root():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/root/autodl-tmp/paper-repro",
    })
    assert runner.remote_workdir == "/root/autodl-tmp/paper-repro"


def test_remote_runner_accepts_private_key_contents():
    pem_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n"
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "ssh_key_path": pem_key,
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
    })
    resolved = runner.normalize_ssh_key_reference(pem_key)
    assert resolved.endswith(".key")
    assert Path(resolved).exists()
    assert "BEGIN" in Path(resolved).read_text(encoding="utf-8")


def test_config_store_and_artifacts(tmp_path):
    config = LocalConfigStore(tmp_path)
    config.save({"cloud_host": "demo.example.com"})
    assert config.load()["cloud_host"] == "demo.example.com"

    collector = ArtifactCollector(tmp_path / "artifacts")
    artifact_dir = collector.collect("task-42", {"status": "success", "logs": "hello"})
    assert (artifact_dir / "task.json").exists()
    assert (artifact_dir / "remote.log").read_text(encoding="utf-8") == "hello"


def test_environment_diagnostics_reports_runtime_profile():
    project_root = Path(__file__).resolve().parents[1]
    diagnosis = EnvironmentDiagnostics(project_root).diagnose()
    assert "python" in diagnosis
    assert diagnosis["profile"]["mode"] in {"conda", "venv", "docker"}
    assert "recommendation" in diagnosis


def test_innovation_analysis_identifies_signal(tmp_path):
    repo_dir = tmp_path / "demo_repo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text(
        "# Attention-aware multi-scale feature fusion for industrial defect detection.\n\nThis method introduces contrastive learning.",
        encoding="utf-8",
    )
    analysis = PaperInnovationAnalyzer().analyze(
        paper_url="https://arxiv.org/abs/2401.00001",
        repo_url="https://github.com/example/project",
        reproduction_logs="Training complete. accuracy 0.95. Feature attention improved results.",
        repo_dir=repo_dir,
    )
    assert analysis["status"] == "success"
    assert analysis["confidence"] > 0.5
    assert any("注意力" in item or "多尺度" in item or "对比" in item for item in analysis["possible_innovations"])


def test_report_generator_creates_markdown_and_json(tmp_path):
    task = {
        "id": "task-001",
        "paper_url": "https://arxiv.org/abs/2201.00001",
        "repo_url": "https://github.com/example/project",
        "status": "success",
        "current_step": "collect",
        "environment_mode": "conda",
    }
    analysis = {
        "summary": "复现结果稳定，创新点集中在多尺度特征融合。",
        "possible_innovations": ["多尺度特征融合：提升小目标检测能力。"],
        "risks": ["需核对数据集版本。"],
        "confidence": 0.82,
    }
    report = generate_repro_report(task, analysis, output_dir=tmp_path)
    assert "论文复现评估报告" in report["report_md"]
    assert report["innovation_count"] == 1
    assert (tmp_path / "task-001_report.md").exists()


def test_summary_and_comparison_helpers_are_usable():
    task = {
        "id": "task-42",
        "paper_url": "https://arxiv.org/abs/2301.00001",
        "repo_url": "https://github.com/example/demo",
        "status": "success",
        "environment_mode": "venv",
    }
    analysis = {
        "summary": "工作稳定，且具有明显的轻量化设计。",
        "possible_innovations": ["轻量化结构设计。"],
        "risks": ["模型需要进一步验证泛化能力。"],
    }
    summary = generate_project_summary(task, analysis, report_path="/tmp/report.md")
    table = generate_experiment_table([
        {"metric": "mAP", "paper": "0.86", "repro": "0.81", "gap": "0.05", "note": "略低但合理"}
    ])
    assert "论文复现项目总结" in summary
    assert "mAP" in table
    assert "0.81" in table


def test_sqlite_open_helper(tmp_path):
    from paper_repro_app.database import TaskStore
    db_file = tmp_path / "test.db"
    store = TaskStore(db_file)
    task = store.create_task(paper_url="http://test.com", repo_url="http://github.com/test/repo", host="1.2.3.4", user="root", port="1234")
    assert task["port"] == "1234"
    assert task["repo_url"] == "http://github.com/test/repo"


def test_auto_repo_dataset_crawler():
    from paper_repro_app.repo_crawler import AutoRepoDatasetCrawler

    crawler = AutoRepoDatasetCrawler()
    res = crawler.evaluate_and_rank_candidates(
        paper_url="https://arxiv.org/abs/2407.02988",
        user_repo_hint="https://github.com/hyphen168/Yolov5m-NEU-DET",
    )
    assert res["best_candidate"] is not None
    assert "Yolov5m-NEU-DET" in res["best_candidate"]["repo_url"]
    assert "dataset_info" in res
    assert res["dataset_info"]["detected"] is False
    assert res["dataset_info"]["mirror_download_url"] == ""



def test_logging_config_and_log_analyzer(tmp_path):
    from paper_repro_app.logging_config import setup_logger
    from paper_repro_app.log_analyzer import LogAnalyzer

    test_log = tmp_path / "logs" / "test.log"
    logger = setup_logger("test_logger", log_file=test_log)
    logger.info("Testing logging config setup")
    logger.error("Fake Error: WinError 10054 Connection refused")

    assert test_log.exists()
    content = test_log.read_text(encoding="utf-8")
    assert "Testing logging config setup" in content
    assert "WinError 10054" in content

    analyzer = LogAnalyzer()
    report = analyzer.analyze_log(content)
    assert report["has_error"] is True
    assert report["error_category"] == "SSH认证与连接"
    assert "WinError 10054" in report["error_snippet"]
    assert "追加到云端的" in report["suggestion"]


def test_detect_remote_workdir_isolates_different_papers():
    dir_paper1 = detect_remote_workdir("https://github.com/hyphen168/Yolov5m-NEU-DET", user="root")
    dir_paper2 = detect_remote_workdir("https://github.com/foo/resnet50-cifar", user="root")
    assert dir_paper1.startswith("/root/autodl-tmp/Yolov5m-NEU-DET__")
    assert dir_paper2.startswith("/root/autodl-tmp/resnet50-cifar__")
    assert dir_paper1 != dir_paper2


def test_remote_runner_resets_workspace_for_same_paper():
    runner = RemoteRunner({
        "host": "example.com",
        "user": "root",
        "repo_url": "https://github.com/hyphen168/Yolov5m-NEU-DET",
        "remote_workdir": "/root/autodl-tmp/Yolov5m-NEU-DET",
    })
    clone_cmd = next(step["command"] for step in runner.build_pipeline() if step["id"] == "clone")
    assert "git reset --hard FETCH_HEAD" in clone_cmd
    assert "git clean -ffdx" in clone_cmd
    assert "rm -rf repo" in clone_cmd


def test_auto_run_command_not_quoted_as_single_word():
    """auto 模式自动命令不得被外层双引号包成单个词（P1-2 回归）。"""
    runner = RemoteRunner({
        "host": "example.com",
        "user": "ubuntu",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "auto_run": True,
        "run_command": "",
    })
    run_cmd = next(step["command"] for step in runner.build_pipeline() if step["id"] == "run")
    # 变量以裸文本出现在命令中交由 bash -c 展开分词（修复前为整词双引号形式）
    assert '${PAPER_REPRO_AUTO_RUN_COMMAND}' in run_cmd
    assert '"${PAPER_REPRO_AUTO_RUN_COMMAND}"' not in run_cmd.replace(chr(92), '')


def test_execute_cancelled_before_connect():
    """取消事件预置时 execute 立即返回 cancelled，且不发起 SSH 连接。"""
    import threading

    runner = RemoteRunner({
        "host": "no-such-host.invalid",
        "user": "ubuntu",
        "repo_url": "https://github.com/example/repro-project",
        "remote_workdir": "/workspace/demo",
        "password": "secret",
    })
    evt = threading.Event()
    evt.set()
    result = runner.execute(cancel_event=evt)
    assert result.get("status") == "cancelled"


def test_cancel_task_idempotent():
    """取消接口对不存在任务/无活动线程均安全返回。"""
    import threading
    from paper_repro_app.storage_utils import cancel_task

    assert cancel_task("__never_exists__") is True
    evt = threading.Event()
    assert not evt.is_set()
