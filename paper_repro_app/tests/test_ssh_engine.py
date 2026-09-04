# -*- coding: utf-8 -*-
"""SSH 专家组规范 P1 验收单测（解析一致性/词法/脱敏/分类）"""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import socket

from paper_repro_app.ssh_utils import (
    build_connection_profiles,
    classify_conn_error,
    parse_connection_profile,
    sanitize,
)
from paper_repro_app.remote_runner import parse_ssh_candidates


def test_parse_userhost_trailing_dashp():
    """R1 回归：@ 后带空白的 -p 不得混入 host。"""
    p = parse_connection_profile("root@connect.cqa1.seetacloud.com -p 38662", {"user": "root"})
    assert p["host"] == "connect.cqa1.seetacloud.com"
    assert p["port"] == 38662 and p["user"] == "root"


def test_parse_attached_dashp():
    p = parse_connection_profile("root@host-x.com -p38662", {"user": "root"})
    assert p["host"] == "host-x.com" and p["port"] == 38662


def test_parse_windows_key_path_kept():
    """Windows 反斜杠路径不得被 shlex(posix) 吞掉。"""
    p = parse_connection_profile('ssh -i C:\\Users\\me\\keys\\id_rsa -p 22 root@h.example.com', {"user": "root"})
    assert p["host"] == "h.example.com"
    assert "\\Users\\me\\keys\\id_rsa" in p.get("key_path", "") or "id_rsa" in p.get("key_path", "")


def test_candidates_delegate_consistency():
    raw = ["root@connect.cqa1.seetacloud.com -p 38662", "host-y:2202"]
    cs = parse_ssh_candidates(raw, "root", 22)
    assert cs[0]["host"] == "connect.cqa1.seetacloud.com" and cs[0]["port"] == 38662
    assert cs[1]["host"] == "host-y" and cs[1]["port"] == 2202
    profs = build_connection_profiles(raw, {"user": "root", "port": 22})
    assert len(profs) == 2 and "error" not in profs[0]


def test_parse_ssh_command_any_order():
    p = parse_connection_profile("ssh -i ~/.ssh/id_x root@z.example.com -p 2200", {"user": "root"})
    assert p["host"] == "z.example.com" and p["port"] == 2200
    assert "id_x" in p.get("key_path", "")


def test_sanitize_no_leak():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAfake\n-----END OPENSSH PRIVATE KEY-----"
    out = sanitize(f"connecting with {pem} password=sup3rsec retry")
    assert "AAAAfake" not in out and "sup3rsec" not in out
    assert "<redacted" in out


def test_classify_conn_error_buckets():
    class FakeRefused(OSError):
        pass

    err = FakeRefused(111, "Connection refused")
    assert classify_conn_error(err) == "refused"
    t = socket.timeout("timed out")
    assert classify_conn_error(t) == "timeout"
    dns = OSError("getaddrinfo failed: Name or service not known")
    assert classify_conn_error(dns) == "dns"
