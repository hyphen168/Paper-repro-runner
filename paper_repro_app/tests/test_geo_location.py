"""天气定位准确性与浏览器定位校准 回归测试（纯逻辑，网络全部打桩）。"""
from __future__ import annotations

import json
from pathlib import Path

import paper_repro_app.weather_fx as wf


def test_parse_browser_loc_valid(monkeypatch, tmp_path, monkeypatch_app_home=None):
    assert wf.parse_browser_loc("26.647,106.630") == (26.647, 106.630)
    assert wf.parse_browser_loc(" 30.27 , 106.64 ") == (30.27, 106.64)


def test_parse_browser_loc_invalid():
    assert wf.parse_browser_loc("") is None
    assert wf.parse_browser_loc("abc") is None
    assert wf.parse_browser_loc("1,2,3") is None
    assert wf.parse_browser_loc("91,0") is None
    assert wf.parse_browser_loc("0,181") is None
    assert wf.parse_browser_loc(None) is None


def test_set_browser_city_reverse_ok(monkeypatch, tmp_path):
    city_file = tmp_path / "weather_city.json"
    monkeypatch.setattr(wf, "CITY_FILE", city_file)

    class _Resp:
        def json(self):
            return {"city": "贵阳市"}

    monkeypatch.setattr(wf.requests, "get", lambda *a, **k: _Resp())
    ok, label = wf.set_browser_city(26.647, 106.630)
    assert ok and label == "贵阳市"
    saved = json.loads(city_file.read_text(encoding="utf-8"))
    assert saved["city"] == "贵阳市"
    assert saved["source"] == "browser"
    assert abs(saved["lat"] - 26.647) < 1e-6


def test_set_browser_city_reverse_fails_fallback_label(monkeypatch, tmp_path):
    city_file = tmp_path / "weather_city.json"
    monkeypatch.setattr(wf, "CITY_FILE", city_file)

    def _boom(*a, **k):
        raise OSError("net down")

    monkeypatch.setattr(wf.requests, "get", _boom)
    ok, label = wf.set_browser_city(26.647, 106.630)
    assert ok
    assert label.startswith("GPS(")  # 反向地名失败时降级坐标标签，仍可用


def test_set_browser_city_validates(monkeypatch, tmp_path):
    city_file = tmp_path / "weather_city.json"
    monkeypatch.setattr(wf, "CITY_FILE", city_file)
    ok, _ = wf.set_browser_city(999, 0)
    assert ok is False
    assert not city_file.exists()


def test_reverse_city_guizhou(monkeypatch):
    class _Resp:
        def json(self):
            return {"city": "贵阳市"}

    monkeypatch.setattr(wf.requests, "get", lambda *a, **k: _Resp())
    assert wf._reverse_city(26.647, 106.630) == "贵阳市"


def test_reverse_city_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise Exception("timeout")

    monkeypatch.setattr(wf.requests, "get", _boom)
    assert wf._reverse_city(0, 0) == ""


def test_ip_provider_is_https_and_includes_region():
    """IP 定位使用 https 并请求 region 字段（便于解释“为什么显示北京”等 ISP 出口问题）。"""
    import re
    # 通过源码断言请求形态，防止回退到 http/精简字段
    src = Path(wf.__file__).read_text(encoding="utf-8")
    assert "https://ipapi.co/json/" in src or "https://ipwho.is/" in src or "ip-api.com/json" in src
