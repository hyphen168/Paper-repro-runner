"""SSH 健壮性回归：任意主机输入（完整 ssh 命令 / user@host / 别名）归一化 + 对比行落库。"""
from __future__ import annotations

import json

import paper_repro_app.ssh_utils as ssh_mod
import paper_repro_app.storage_utils as su
from paper_repro_app.ssh_utils import resolve_connection_fields


def test_resolve_connection_fields_full_ssh_command():
    out = resolve_connection_fields("ssh -p 13150 root@connect.cqa1.seetacloud.com")
    assert out["host"] == "connect.cqa1.seetacloud.com"
    assert out["port"] == "13150"
    assert out["user"] == "root"


def test_resolve_connection_fields_with_key():
    out = resolve_connection_fields("ssh -i ~/.ssh/id_ed25519 -p 38662 root@connect.cqa1.seetacloud.com", key="fallback")
    assert out["host"] == "connect.cqa1.seetacloud.com"
    assert out["key"] == "~/.ssh/id_ed25519"
    assert out["port"] == "38662"


def test_resolve_connection_fields_plain_host_keeps_fallback():
    out = resolve_connection_fields("1.2.3.4", user="alice", port="2222")
    assert out["host"] == "1.2.3.4"
    assert out["user"] == "alice"
    assert out["port"] == "2222"


def test_resolve_connection_fields_garbage_never_raises():
    for garbage in ("", "   ", "ssh -p", "!!!###", "http://x" * 3):
        out = resolve_connection_fields(garbage)
        assert isinstance(out, dict) and out.get("host") is not None


def test_resolve_connection_fields_multiline_prefers_first():
    out = resolve_connection_fields("ssh -p 1111 root@old.example.com\nssh -p 2222 root@new.example.com")
    assert out["host"] == "old.example.com"
    assert out["port"] == "1111"


def test_test_ssh_connection_normalizes_raw_command():
    """即使直接把完整 ssh 命令塞进 host，也不应把它当主机名，给出友好错误而非崩溃。"""
    ok, msg = ssh_mod.test_ssh_connection(
        host="ssh -p 13150 root@connect.invalid-no-such-host.invalid",
        user="",
        port="",
        key="",
    )
    assert ok is False
    assert isinstance(msg, str) and len(msg) < 500


def test_parse_ssh_config_no_match_returns_empty_not_crash(tmp_path, monkeypatch):
    """~/.ssh/config 存在但没有目标主机 Host 块 → 返回 {}，绝不 IndexError。"""
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host papercloud\n  HostName connect.cqa1.seetacloud.com\n  User root\n  Port 34367\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "paper_repro_app.ssh_utils.get_ssh_config_path", lambda: cfg)
    out = ssh_mod.parse_ssh_config("connect.other.example.com")
    assert out == {}


def test_parse_ssh_config_matching_host_returns_profile(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host papercloud\n  HostName connect.cqa1.seetacloud.com\n  User root\n  Port 13150\n"
        "  IdentityFile ~/.ssh/id_ed25519\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "paper_repro_app.ssh_utils.get_ssh_config_path", lambda: cfg)
    out = ssh_mod.parse_ssh_config("connect.cqa1.seetacloud.com")
    assert out.get("host") == "connect.cqa1.seetacloud.com"
    assert out.get("port") == "13150"


def test_resolve_ssh_profile_typing_new_server_no_crash(tmp_path, monkeypatch):
    """输入新服务器 ssh 命令 + 配置文件只含旧机器 → 正常回落，不抛 IndexError。"""
    cfg = tmp_path / "config"
    cfg.write_text("Host papercloud\n  HostName old.example.com\n  User root\n", encoding="utf-8")
    monkeypatch.setattr(
        "paper_repro_app.ssh_utils.get_ssh_config_path", lambda: cfg)
    profile = ssh_mod.resolve_ssh_profile(
        "ssh -p 13150 root@connect.new.example.com",
        fallback_host="", fallback_user="", fallback_key="",
    )
    assert profile["host"] == "connect.new.example.com"
    assert profile["port"] == "13150"
    assert profile["user"] == "root"
def test_comparison_rows_persisted_into_result(tmp_path, monkeypatch):
    """build_comparison_table 后 result 里应带结构化 comparison_rows（供对比图）。"""
    monkeypatch.setattr(su, "DB_PATH", tmp_path / "tasks.db")
    result = {"status": "success", "metrics": {}, "logs": ""}
    task = {
        "paper_url": "https://arxiv.org/abs/0000.0000",
        "repo_url": "https://github.com/nonexistent/nonexistent",
        "run_command": "",
    }
    su.build_comparison_table(result, task)
    assert "comparison_rows" in result
    rows = result["comparison_rows"]
    assert isinstance(rows, list) and rows, "至少应含无基准说明行"
    assert {"metric", "paper", "repro", "gap", "note"} <= set(rows[0].keys())
    # 无指标也不影响 JSON 序列化（结果落库必经路径）
    json.dumps(result, ensure_ascii=False)
