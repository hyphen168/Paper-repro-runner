# -*- coding: utf-8 -*-
"""repo_profiles 单元测试"""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from paper_repro_app import repo_profiles as rp


def test_normalize():
    assert rp.normalize_repo_url("https://github.com/a/b.git/") == "https://github.com/a/b"
    assert rp.normalize_repo_url("https://ghfast.top/https://github.com/a/b") == "https://github.com/a/b"
    assert rp.normalize_repo_url("git@github.com:a/b.git") == "https://github.com/a/b"


def test_upsert_and_get(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "PROFILE_FILE", tmp_path / "repo_profiles.json")
    rp.upsert_profile("https://github.com/akamaster/pytorch_resnet_cifar10", {
        "status": "success", "entrypoint": "trainer.py",
        "run_command": "python trainer.py --arch resnet20 --epochs 200",
        "data_config": "__repo_managed__", "host_hint": {"host": "h1", "auth_kind": "password"},
    })
    got = rp.get_for_repo("https://github.com/akamaster/pytorch_resnet_cifar10")
    assert got and got["entrypoint"] == "trainer.py"
    assert got["run_count"] == 1 and got["last_status"] == "success"
    # 别名三段匹配
    assert rp.get_for_repo("https://github.com/akamaster/pytorch_resnet_cifar10") is not None


def test_failure_does_not_overwrite_success(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "PROFILE_FILE", tmp_path / "repo_profiles.json")
    rp.upsert_profile("https://github.com/a/b", {"status": "success", "run_command": "cmd-ok"})
    rp.upsert_profile("https://github.com/a/b", {"status": "failed", "fail_tag": "E_TORCH_CPU"})
    got = rp.get_for_repo("https://github.com/a/b")
    assert got["last_status"] == "success"          # 成功优先保留
    assert got["run_command"] == "cmd-ok"
    assert "E_TORCH_CPU" in got["fail_reason_tags"]


def test_remove(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "PROFILE_FILE", tmp_path / "repo_profiles.json")
    rp.upsert_profile("https://github.com/a/b", {"status": "success"})
    assert rp.remove_profile("https://github.com/a/b") is True
    assert rp.get_for_repo("https://github.com/a/b") is None
