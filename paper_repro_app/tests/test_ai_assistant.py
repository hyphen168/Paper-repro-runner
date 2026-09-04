# -*- coding: utf-8 -*-
"""ai_client / ai_config 单元测试（mock 网关）"""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import json

import pytest
import requests

from paper_repro_app.ai_client import PROVIDERS, chat_once, estimate_tokens, sanitize_for_llm
from paper_repro_app import ai_config as cfg


class _FakeResp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


def test_sanitize_for_llm():
    out = sanitize_for_llm("key=sk-abc12345678901234567890 call https://x/d?X-Amz-Signature=deadbeef12345678&x=1")
    assert "sk-abc1234567890" not in out and "deadbeef12345678" not in out
    assert "sk-<redacted>" in out and "<redacted>" in out
    out2 = sanitize_for_llm("password=sup3rs3cret and PEM -----BEGIN RSA PRIVATE KEY-----abc-----END RSA PRIVATE KEY-----")
    assert "sup3rs3cret" not in out2 and "abc" not in out2


def test_estimate_tokens():
    assert estimate_tokens("你好世界") >= 6
    assert estimate_tokens("hello world") < 10


def test_providers_present():
    assert "DeepSeek" in PROVIDERS and "通义 Qwen" in PROVIDERS and "自定义" not in PROVIDERS


def test_chat_once_ok(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResp(200, json_data={"choices": [{"message": {"content": "你好，我是 AI"}}]})
    monkeypatch.setattr(requests, "post", fake_post)
    ok, text = chat_once([{"role": "user", "content": "hi"}], "https://x/v1", "sk-test-1234567890", "m")
    assert ok and "你好" in text


def test_chat_once_err(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResp(401, text="unauthorized")
    monkeypatch.setattr(requests, "post", fake_post)
    ok, msg = chat_once([{"role": "user", "content": "hi"}], "https://x/v1", "sk-bad", "m")
    assert not ok and "401" in msg


def test_config_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CRED_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CRED_FILE", tmp_path / "llm_credentials.bin")
    ok = cfg.save_credentials({"provider": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
                               "model": "deepseek-chat", "api_key": "sk-secret-123456789012345"})
    assert ok
    loaded = cfg.load_credentials()
    assert loaded["api_key"] == "sk-secret-123456789012345"
    assert loaded["provider"] == "DeepSeek"
    assert cfg.api_key_tail(loaded["api_key"]) == "…2345"
    cfg.clear_credentials()
    assert cfg.load_credentials()["api_key"] == ""
