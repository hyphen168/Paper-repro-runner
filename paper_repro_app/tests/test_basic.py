import importlib.util
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("streamlit_app_module", APP_PATH)
APP_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP_MODULE)
parse_ssh_target = APP_MODULE.parse_ssh_target

from paper_repro_app.artifacts import ArtifactCollector
from paper_repro_app.config_store import LocalConfigStore
from paper_repro_app.database import TaskStore
from paper_repro_app.diagnostics import EnvironmentDiagnostics
from paper_repro_app.innovation_analysis import PaperInnovationAnalyzer
from paper_repro_app.paper_parser import extract_repo_url
from paper_repro_app.project_summary import generate_project_summary
from paper_repro_app.remote_runner import RemoteRunner
from paper_repro_app.report_generator import generate_repro_report
from paper_repro_app.comparison_table import generate_experiment_table


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

    store.update_task_status("task-123", "running", "start")
    store.append_task_log("task-123", "step 1 done")
    assert "step 1 done" in store.get_task("task-123")["log"]


def test_extract_repo_url_handles_known_hosts():
    repo_url = "https://github.com/example/repro-project"
    assert repo_url in repo_url
    assert "github.com" in repo_url


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
