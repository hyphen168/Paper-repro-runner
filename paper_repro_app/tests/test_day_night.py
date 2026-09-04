
"""实时昼夜系统单元测试（纯数学，零依赖）。"""
from datetime import datetime, timedelta
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from paper_repro_app.day_night import (PALETTES, PHASE_IDS, build_events, css_vars_block,
                                       find_crossing, load_location, sample_vars,
                                       solar_elevation_azimuth)

SH = (31.2, 121.45)


def test_solar_noon_autumn_equinox():
    """φ40N 秋分正午：高度≈50°、方位≈180°（正南）。"""
    alt, az = solar_elevation_azimuth(80, 12.0, 40.0, 0.0)
    assert abs(alt - 50.0) < 1.0
    assert abs(az - 180.0) < 4.0


def test_solar_range():
    for h in range(0, 24):
        alt, az = solar_elevation_azimuth(100, h, 31.2, 121.45)
        assert -90.0 <= alt <= 90.0
        assert 0.0 <= az <= 360.0


def test_day_night_sequence_shanghai():
    """上海 9 月某日：深宵→日出→正午最亮→黄金→夜晚。"""
    base = datetime(2026, 9, 4)
    prev = None
    seq = []
    for m in range(0, 24 * 60, 10):
        v = sample_vars(base + timedelta(minutes=m), *SH, prev=prev)
        prev = v
        seq.append(v)
    # 深宵 df 低
    assert seq[0]["day_factor"] < 0.1 and seq[0]["phase"] == "P1_DeepNight"
    # 白天太阳可见
    day_vals = [v for v in seq if v["sun_a"] > 0.5]
    assert day_vals, "白天应有太阳"
    assert max(v["day_factor"] for v in seq) > 0.55, "正午应显著亮于深夜"
    # 夜晚太阳隐藏
    night = [v for v in seq if v["phase"] == "P1_DeepNight"]
    assert all(v["sun_a"] < 0.1 for v in night)


def test_outputs_bounded():
    base = datetime(2026, 9, 4)
    v = sample_vars(base + timedelta(hours=12), *SH)
    for k in ("sun_x", "sun_y", "moon_x", "moon_y"):
        assert 0 <= v[k] <= 100
    for k in ("day_factor", "sun_a", "moon_a", "star_alpha", "glow_c", "glow_m", "glow_y",
              "card_alpha", "particle_bright"):
        assert 0.0 <= v[k] <= 1.0
    assert v["sky_top"].startswith("#") and len(v["sky_top"]) == 7
    css = css_vars_block(v)
    assert "--sky-top" in css and "--day-factor" in css


def test_palettes_complete():
    assert len(PHASE_IDS) == 9
    for pid in PHASE_IDS:
        p = PALETTES[pid]
        assert p["top"].startswith("#") and p["hor"].startswith("#")
        assert 0 <= p["df"] <= 1
