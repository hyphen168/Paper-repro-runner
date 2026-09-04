"""当地时刻服务 + day_night 当地偏移兼容性单测（纯数学/文件级，零网络）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from paper_repro_app import localtime
from paper_repro_app.day_night import build_events, sample_vars

SH = (31.2, 121.45)  # 上海


def _write_cache(tmp_path: Path, payload: dict) -> Path:
    cache = tmp_path / "weather_cache.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return cache


# ================= get_location_offset_seconds =================
def test_offset_from_cache_key(monkeypatch, tmp_path):
    cache = _write_cache(tmp_path, {"lat": 31.2, "lon": 121.45, "utc_offset_seconds": 28800})
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.get_location_offset_seconds() == 28800


def test_offset_fallback_lon_when_key_missing(monkeypatch, tmp_path):
    """旧缓存无 utc_offset_seconds 时按 lon 近似（121.45E → +8h）。"""
    cache = _write_cache(tmp_path, {"lat": 31.2, "lon": 121.45})
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.get_location_offset_seconds() == 8 * 3600


def test_offset_none_when_no_cache(monkeypatch, tmp_path):
    cache = tmp_path / "missing.json"
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.get_location_offset_seconds() is None


def test_offset_none_on_corrupt_cache(monkeypatch, tmp_path):
    cache = tmp_path / "weather_cache.json"
    cache.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.get_location_offset_seconds() is None


def test_offset_rejects_out_of_range(monkeypatch, tmp_path):
    cache = _write_cache(tmp_path, {"utc_offset_seconds": 999999, "lon": 121.45})
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.get_location_offset_seconds() is None


def test_lon_offset_seconds():
    assert localtime.lon_offset_seconds(121.45) == 8 * 3600
    assert localtime.lon_offset_seconds(-75.0) == -5 * 3600
    assert localtime.lon_offset_seconds(0.0) == 0
    assert localtime.lon_offset_seconds(None) == 0
    assert localtime.lon_offset_seconds("oops") == 0


# ================= location_utc_offset_seconds / location_now =================
def test_location_utc_offset_seconds_machine_fallback(monkeypatch, tmp_path):
    cache = tmp_path / "missing.json"
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    machine = int(datetime.now().astimezone().utcoffset().total_seconds())
    assert localtime.location_utc_offset_seconds() == machine


def test_location_utc_offset_seconds_prefers_cache(monkeypatch, tmp_path):
    cache = _write_cache(tmp_path, {"lon": 121.45, "utc_offset_seconds": 28800})
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    assert localtime.location_utc_offset_seconds() == 28800


def test_location_now_with_offset(monkeypatch, tmp_path):
    cache = _write_cache(tmp_path, {"lon": 121.45, "utc_offset_seconds": 28800})
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    now = localtime.location_now()
    expected = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=28800)
    assert abs((now - expected).total_seconds()) < 5
    assert now.tzinfo is None, "返回 naive 当地时间"


def test_location_now_fallback_machine(monkeypatch, tmp_path):
    cache = tmp_path / "missing.json"
    monkeypatch.setattr(localtime, "WEATHER_CACHE_FILE", cache)
    now = localtime.location_now()
    assert abs((now - datetime.now()).total_seconds()) < 5


# ================= format_hhmm =================
def test_format_hhmm():
    assert localtime.format_hhmm(datetime(2026, 9, 4, 7, 5)) == "07:05"
    assert localtime.format_hhmm(datetime(2026, 9, 4, 23, 59)) == "23:59"
    text = localtime.format_hhmm()  # 空参 → 当地时刻
    assert len(text) == 5 and text[2] == ":" and text[:2].isdigit() and text[3:].isdigit()


# ================= day_night 显式当地偏移兼容 =================
def test_day_night_sample_vars_offsets_equivalent():
    """同一绝对 UTC 时刻以 +8h / 0h 两种墙上时钟表示 → 太阳位置一致。"""
    base_utc = datetime(2026, 9, 4, 6, 0)
    v_plus8 = sample_vars(base_utc + timedelta(hours=8), SH[0], SH[1], utc_offset_s=8 * 3600)
    v_zero = sample_vars(base_utc + timedelta(hours=0), SH[0], SH[1], utc_offset_s=0)
    for key in ("solar_alt", "sun_x", "sun_y", "sun_a"):
        assert abs(v_plus8[key] - v_zero[key]) < 1e-9, f"{key} 应只依赖真实 UTC 时刻"


def test_day_night_build_events_accepts_offset():
    base = datetime(2026, 9, 4)
    edges, seg = build_events(base, SH[0], SH[1], utc_offset_s=8 * 3600)
    assert edges and len(edges) >= 2 and seg
    assert edges[0] == 0.0 and edges[-1] == 1440.0
    edges_legacy, seg_legacy = build_events(base, SH[0], SH[1])
    assert edges_legacy[0] == 0.0 and edges_legacy[-1] == 1440.0


def test_day_night_sample_vars_legacy_default_matches_old_signature():
    """不带 utc_offset_s 时保持旧签名行为（关键键存在且有界）。"""
    v = sample_vars(datetime(2026, 9, 4, 12, 0), SH[0], SH[1])
    assert {"day_factor", "sun_a", "solar_alt", "phase"} <= set(v.keys())
    assert 0.0 <= v["sun_a"] <= 1.0
