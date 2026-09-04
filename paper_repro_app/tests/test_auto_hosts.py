"""自动识别候选主机解析（多机器/动态实例）。"""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from paper_repro_app.remote_runner import parse_ssh_candidates


def test_parse_basic_hosts():
    cs = parse_ssh_candidates(["123.45.67.89", "58.144.141.28:28905"], "root", 22)
    assert cs[0] == {"host": "123.45.67.89", "port": 22, "user": "root"}
    assert cs[1] == {"host": "58.144.141.28", "port": 28905, "user": "root"}


def test_parse_user_host():
    cs = parse_ssh_candidates(["admin@my.server.com"], "root", 22)
    assert cs[0] == {"host": "my.server.com", "port": 22, "user": "admin"}


def test_parse_autodl_ssh_command():
    cs = parse_ssh_candidates(["ssh -p 38662 root@connect.cqa1.seetacloud.com"], "root", 22)
    assert cs[0] == {"host": "connect.cqa1.seetacloud.com", "port": 38662, "user": "root"}


def test_parse_skips_blank_and_comment():
    cs = parse_ssh_candidates(["", "   ", "# note", "host-a:2202"], "root", 22)
    assert len(cs) == 1 and cs[0]["port"] == 2202


def test_parse_dedup():
    cs = parse_ssh_candidates(["root@a:22", "a:22", "root@a:22"], "root", 22)
    assert len(cs) == 1
