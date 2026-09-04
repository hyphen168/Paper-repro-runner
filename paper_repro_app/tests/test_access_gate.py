# -*- coding: utf-8 -*-
"""access_gate v2 单测（口令 + 受信令牌）"""
from pathlib import Path
import sys
import time

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import pytest

from paper_repro_app import access_gate as ag


@pytest.fixture
def gate(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "ACCESS_FILE", tmp_path / "access.json")
    assert ag.set_access_code("abcd1234")
    return ag


def test_code_roundtrip(gate):
    assert gate.is_configured()
    assert gate.verify_access_code("abcd1234")
    assert not gate.verify_access_code("wrong")


def test_token_issue_verify(gate):
    raw = gate.issue_device_token("我的手机")
    assert raw and len(raw) > 20
    assert gate.verify_device_token(raw)
    assert not gate.verify_device_token("bad-token")


def test_token_revoke(gate):
    raw = gate.issue_device_token()
    tokens = gate.list_device_tokens()
    assert len(tokens) == 1
    assert gate.revoke_device_token(tokens[0]["id"])
    assert not gate.verify_device_token(raw)


def test_token_expired(gate, monkeypatch):
    monkeypatch.setattr(ag, "_ttl_days", lambda: 0)  # expires_at=0 = 永不过期
    raw = gate.issue_device_token()
    # 手改 expires_at 为过去
    import json
    p = ag.ACCESS_FILE
    data = json.loads(p.read_text(encoding="utf-8"))
    data["tokens"][0]["expires_at"] = int(time.time()) - 10
    p.write_text(json.dumps(data), encoding="utf-8")
    assert not gate.verify_device_token(raw)


def test_reset_code_revokes_all(gate):
    raw = gate.issue_device_token()
    assert gate.verify_device_token(raw)
    assert gate.set_access_code("newpass123")  # 重设口令 epoch+1
    assert not gate.verify_device_token(raw)
    assert gate.list_device_tokens() == []


def test_revoke_all(gate):
    raw = gate.issue_device_token()
    assert gate.revoke_all_tokens()
    assert not gate.verify_device_token(raw)
