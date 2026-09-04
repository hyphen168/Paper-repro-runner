"""实时白天黑夜系统（依据 docs/day_night_research.md 落地）。

- 天文：NOAA 简化法太阳高度角/方位角（误差 ±0.2°）；二分求日出/日没（−0.833°）
- 定位：优先使用天气缓存经纬度；无定位回退 φ=32° + Cooper 赤纬近似
- 时间轴：12 边界事件表驱动（日出 RS / 日没 SS ± 偏移），60s 粒度采样
- 相位：9 阶段（深宵→黎明→日出→清晨→正午→午后→黄金→蓝调→夜晚）
- 输出：CSS 变量字典（天空三色/日月坐标/霓虹系数/玻璃卡/粒子亮度），含线性域混色与限幅
零第三方依赖、零 UI 依赖（可纯单测）。
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from paper_repro_app.paths import APP_HOME

_WEATHER_CACHE = APP_HOME / "weather_cache.json"
_TWO_PI = 2.0 * math.pi


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _day_of_year(dt: datetime) -> int:
    return dt.timetuple().tm_yday


def solar_elevation_azimuth(day_of_year: int, utc_hours: float, lat: float, lon: float):
    """NOAA 简化法：返回 (高度角°, 方位角°自北顺时针)。"""
    g = _TWO_PI / 365.0 * (day_of_year - 1 + (utc_hours - 12.0) / 24.0)
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
           - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
           - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = utc_hours + lon / 15.0 + eot / 60.0
    h_angle = math.radians(15.0 * (tst - 12.0))
    phi = math.radians(lat)
    s_alt = clamp(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(h_angle))
    alt = math.degrees(math.asin(s_alt))
    denom = math.cos(math.radians(alt)) * math.cos(phi)
    az = 0.0
    if abs(denom) > 1e-9 and abs(alt) < 89.9:
        az = math.degrees(math.acos(clamp(
            (math.sin(dec) - math.sin(math.radians(alt)) * math.sin(phi)) / denom)))
        if h_angle > 0:
            az = 360.0 - az
    return alt, az


def find_crossing(day_of_year: int, lat: float, lon: float, rising: bool) -> Optional[float]:
    """二分找太阳上缘过地平线（−0.833°）时刻（UTC 小时）。

    以当日太阳高度最大值（正午）为界：日出在 [0, tmax]，日落在 [tmax, 24]。
    极昼（全天 min>target）/极夜（全天 max<target）返回 None。
    """
    target = -0.833
    # 当日高度 min/max（每 30 分钟采样）
    samples = [solar_elevation_azimuth(day_of_year, hh, lat, lon)[0] for hh in
               [i * 0.5 for i in range(48)]]
    alt_min, alt_max = min(samples), max(samples)
    if alt_max < target:
        return None  # 极夜
    if alt_min > target:
        return None  # 极昼
    tmax = samples.index(alt_max) * 0.5
    lo_h, hi_h = (0.0, tmax) if rising else (tmax, 24.0)
    lo_alt = solar_elevation_azimuth(day_of_year, lo_h, lat, lon)[0]
    hi_alt = solar_elevation_azimuth(day_of_year, hi_h, lat, lon)[0]
    # 若端点未跨 target（罕见：极昼边缘或 tmax 采样偏差），直接 None 兜底
    if (lo_alt - target) * (hi_alt - target) > 0:
        return None
    for _ in range(30):
        mid = (lo_h + hi_h) / 2.0
        alt = solar_elevation_azimuth(day_of_year, mid, lat, lon)[0]
        if rising:
            if alt > target:
                hi_h = mid
            else:
                lo_h = mid
        else:
            if alt > target:
                lo_h = mid
            else:
                hi_h = mid
    return (lo_h + hi_h) / 2.0


def load_location() -> Optional[dict]:
    """优先读天气缓存经纬度；失败返回 None（调用方走 fallback）。"""
    try:
        data = json.loads(_WEATHER_CACHE.read_text(encoding="utf-8"))
        lat = float(data.get("lat") or 0)
        lon = float(data.get("lon") or 0)
        if lat or lon:
            return {"lat": lat, "lon": lon}
    except (OSError, ValueError, TypeError):
        pass
    return None


# ============ 九阶段调色板（B.2/B.4/B.5 数值） ============
# 索引与事件表段对应：0=P1 深宵 … 8=P9 夜晚
PHASE_IDS = ["P1_DeepNight", "P2_PreDawn", "P3_SunriseDawn", "P4_Morning", "P5_Midday",
             "P6_Afternoon", "P7_GoldenDusk", "P8_BlueHour", "P9_Nightfall"]

PALETTES: Dict[str, dict] = {
    "P1_DeepNight":     {"top": "#03050D", "mid": "#070C1D", "hor": "#0D1530", "df": 0.00,
                         "glow_c": 0.85, "glow_m": 1.00, "glow_y": 0.40, "ca": 0.50, "cb": 0, "star": 1.00},
    "P2_PreDawn":       {"top": "#060B1C", "mid": "#0E1D3E", "hor": "#1E3F6E", "df": 0.08,
                         "glow_c": 0.70, "glow_m": 0.80, "glow_y": 0.35, "ca": 0.50, "cb": 2, "star": 0.85},
    "P3_SunriseDawn":   {"top": "#0A1128", "mid": "#22375F", "hor": "#D79B4E", "df": 0.30,
                         "glow_c": 0.50, "glow_m": 0.45, "glow_y": 0.75, "ca": 0.52, "cb": 4, "star": 0.50},
    "P4_Morning":       {"top": "#16294C", "mid": "#2C4770", "hor": "#5A7394", "df": 0.60,
                         "glow_c": 0.35, "glow_m": 0.25, "glow_y": 0.55, "ca": 0.55, "cb": 6, "star": 0.15},
    "P5_Midday":        {"top": "#24406B", "mid": "#33547F", "hor": "#5F7BA0", "df": 1.00,
                         "glow_c": 0.30, "glow_m": 0.20, "glow_y": 0.45, "ca": 0.60, "cb": 8, "star": 0.00},
    "P6_Afternoon":     {"top": "#1A2C4E", "mid": "#2B4260", "hor": "#CF9A5A", "df": 0.60,
                         "glow_c": 0.35, "glow_m": 0.30, "glow_y": 0.60, "ca": 0.55, "cb": 6, "star": 0.15},
    "P7_GoldenDusk":    {"top": "#0C1230", "mid": "#33305C", "hor": "#FF9E4F", "df": 0.35,
                         "glow_c": 0.45, "glow_m": 0.55, "glow_y": 1.00, "ca": 0.52, "cb": 4, "star": 0.40},
    "P8_BlueHour":      {"top": "#070E2C", "mid": "#123464", "hor": "#3D5F9E", "df": 0.12,
                         "glow_c": 0.75, "glow_m": 0.80, "glow_y": 0.30, "ca": 0.50, "cb": 2, "star": 0.75},
    "P9_Nightfall":     {"top": "#050A1E", "mid": "#0B1736", "hor": "#1E3258", "df": 0.04,
                         "glow_c": 0.80, "glow_m": 0.95, "glow_y": 0.35, "ca": 0.50, "cb": 0, "star": 0.95},
}

# ============ 颜色工具 ============
def _hex_to_linear(h: str):
    h = h.lstrip("#")
    return [(_c / 255.0) ** 2.2 for _c in (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))]


def _linear_to_hex(rgb):
    return "#" + "".join("%02X" % clamp(round((c ** (1 / 2.2)) * 255), 0, 255) for c in rgb)


def mix_hex(a: str, b: str, t: float) -> str:
    """线性域混合两 HEX。"""
    la, lb = _hex_to_linear(a), _hex_to_linear(b)
    return _linear_to_hex([la[i] + (lb[i] - la[i]) * t for i in range(3)])


def smoothstep(x: float) -> float:
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _solar_screen(lat: float, alt: float, az: float, dec_deg: float, rising: bool):
    """太阳屏幕坐标 %（东左西右、地平 72%、天顶 8%）与 alpha。"""
    a_noon = 180.0 if lat >= 0 else 0.0
    x = 50.0 + 50.0 * math.sin(math.radians(az - a_noon))
    h_max = max(90.0 - abs(lat - dec_deg), 6.0)
    ratio = clamp(math.sin(math.radians(max(alt, 0.0))) / math.sin(math.radians(h_max)), 0.0, 1.0)
    y = 72.0 - 64.0 * ratio
    if alt >= -0.833:
        a = 1.0
    elif alt >= -6.0:
        a = (alt + 6.0) / 5.167
    else:
        a = 0.0
    return {"x": x, "y": y, "a": a}


def _moon_screen(lat: float, az_sun: float, alt: float):
    """月亮视觉近似（对跖方位 + 固定高度），alpha 仅夜间显现。"""
    az_moon = az_sun + 180.0
    if az_moon >= 360.0:
        az_moon -= 360.0
    a_noon = 180.0 if lat >= 0 else 0.0
    x = 50.0 + 50.0 * math.sin(math.radians(az_moon - a_noon))
    y = 72.0 - 60.0 * 0.5  # 固定约 42%
    if alt < -18.0:
        a = 1.0
    elif alt < -8.0:
        a = (alt + 18.0) / 10.0
    else:
        a = 0.0
    return {"x": x, "y": y, "a": a}


# ============ 采样主入口 ============
def _alt_at_local_minute(base: datetime, minute: int, lat: float, lon: float) -> float:
    """本地钟面第 minute 分钟的太阳高度（自动处理 UTC 跨日）。"""
    t = base + timedelta(minutes=minute) - timedelta(seconds=time.localtime().tm_gmtoff)
    day = _day_of_year(t)
    utc_h = t.hour + t.minute / 60.0 + t.second / 3600.0
    return solar_elevation_azimuth(day, utc_h, lat, lon)[0]


def build_events(base: datetime, lat: float, lon: float):
    """返回当日（本地钟面）事件表（分钟）与各段起始相位；极昼/极夜兜底。

    用 10 分钟扫描检测太阳高度穿越 −0.833°（正穿=日出、负穿=日落），
    避免“UTC 跨日”导致二分区间端点同为黑夜/白昼的误判。
    """
    target = -0.833
    rises, sets = [], []
    prev = None
    for m in range(0, 1441, 10):
        alt = _alt_at_local_minute(base, m, lat, lon)
        if prev is not None:
            if prev <= target < alt:
                rises.append(m - 10 + 10 * (target - prev) / (alt - prev))
            elif alt <= target < prev:
                sets.append(m - 10 + 10 * (target - prev) / (alt - prev))
        prev = alt
    # 无穿越：极昼/极夜按正午高度判定
    if not rises or not sets:
        noon_alt = _alt_at_local_minute(base, 720, lat, lon)
        if noon_alt > 0:
            return [0.0, 1440.0], [4]  # 全天正午白天
        return [0.0, 1440.0], [0]      # 全天深宵
    rs_m = rises[0]
    ss_m = sets[-1]
    edges = [0.0, rs_m - 90.0, rs_m - 30.0, rs_m + 30.0, rs_m + 125.0,
             ss_m - 125.0, ss_m - 30.0, ss_m + 20.0, ss_m + 40.0, ss_m + 90.0, 1440.0]
    edges = [max(0.0, min(1440.0, e)) for e in edges]
    # 按序去重/保序（极端纬度相邻事件可能重叠）
    dedup = []
    for e in edges:
        if not dedup or e > dedup[-1] + 1:
            dedup.append(e)
    if dedup[-1] < 1440.0:
        dedup.append(1440.0)
    seg = [0, 1, 2, 3, 4, 5, 6, 7, 8, 0][: max(len(dedup) - 1, 1)]
    while len(seg) < len(dedup) - 1:
        seg.append(seg[-1])
    return dedup, seg[:len(dedup) - 1]


def sample_vars(now: datetime, lat: float, lon: float, prev: Optional[dict] = None) -> dict:
    """当前时刻采样 → CSS 变量字典。prev 用于限幅防跳变。"""
    # 本地时刻 → UTC（tm_gmtoff = 本地 − UTC 秒）
    utc_dt = now - timedelta(seconds=time.localtime().tm_gmtoff)
    day = _day_of_year(utc_dt)
    utc = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    alt, az = solar_elevation_azimuth(day, utc, lat, lon)
    # 赤纬（用于 h_max）
    g = _TWO_PI / 365.0 * (day - 1 + (utc - 12.0) / 24.0)
    dec = math.degrees(0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
                       - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
                       - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    base_day = datetime(now.year, now.month, now.day)
    edges, seg = build_events(base_day, lat, lon)

    now_m = now.hour * 60.0 + now.minute + now.second / 60.0
    idx = len(edges) - 2
    for i in range(len(edges) - 1):
        if edges[i] <= now_m < edges[i + 1]:
            idx = i
            break
    nxt = min(idx + 1, len(seg) - 1)
    span = max(edges[idx + 1] - edges[idx], 1.0)
    u = smoothstep((now_m - edges[idx]) / span)
    pa = PALETTES[PHASE_IDS[seg[idx]]]
    pb = PALETTES[PHASE_IDS[seg[nxt]]]

    def mix(k, pa=pa, pb=pb, u=u):
        return pa[k] + (pb[k] - pa[k]) * u

    sky_top = mix_hex(pa["top"], pb["top"], u)
    sky_mid = mix_hex(pa["mid"], pb["mid"], u)
    sky_hor = mix_hex(pa["hor"], pb["hor"], u)
    day_factor = mix("df")
    rising = alt >= -0.0
    sun = _solar_screen(lat, alt, az, dec, rising)
    moon = _moon_screen(lat, az, alt)

    out = {
        "dn_t": now_m / 1440.0,
        "day_factor": day_factor,
        "sky_top": sky_top,
        "sky_mid": sky_mid,
        "sky_hor": sky_hor,
        "sun_x": sun["x"], "sun_y": sun["y"], "sun_a": sun["a"],
        "moon_x": moon["x"], "moon_y": moon["y"], "moon_a": moon["a"],
        "star_alpha": mix("star"),
        "glow_c": mix("glow_c"), "glow_m": mix("glow_m"), "glow_y": mix("glow_y"),
        "card_alpha": mix("ca"), "card_bright": mix("cb"),
        "particle_bright": 0.55 + 0.45 * day_factor,
        "phase": PHASE_IDS[seg[idx]],
        "solar_alt": alt,
    }
    # 限幅防跳变（60s tick）
    if prev:
        out["day_factor"] = prev.get("day_factor", day_factor) + clamp(
            day_factor - prev.get("day_factor", day_factor), -0.02, 0.02)
        for key in ("sky_top", "sky_mid", "sky_hor"):
            out[key] = mix_hex(prev.get(key, out[key]), out[key], 0.15) if prev.get(key) else out[key]
    return out


def css_vars_block(v: dict) -> str:
    """把采样结果渲染为 <style> CSS 变量块。"""
    return (
        "<style>:root{"
        f"--day-factor:{v['day_factor']:.3f};"
        f"--sky-top:{v['sky_top']};--sky-mid:{v['sky_mid']};--sky-hor:{v['sky_hor']};"
        f"--sun-x:{v['sun_x']:.1f}%;--sun-y:{v['sun_y']:.1f}%;--sun-a:{v['sun_a']:.2f};"
        f"--moon-x:{v['moon_x']:.1f}%;--moon-y:{v['moon_y']:.1f}%;--moon-a:{v['moon_a']:.2f};"
        f"--star-alpha:{v['star_alpha']:.2f};"
        f"--glow-c:{v['glow_c']:.2f};--glow-m:{v['glow_m']:.2f};--glow-y:{v['glow_y']:.2f};"
        f"--card-alpha:{v['card_alpha']:.2f};--card-bright:{v['card_bright']:.0f}%;"
        f"--particle-bright:{v['particle_bright']:.2f};"
        "}</style>"
    )


def now_day_night_vars(prev: Optional[dict] = None) -> dict:
    """便捷入口：取定位并采样当前时刻。"""
    loc = load_location() or {"lat": 32.0, "lon": 0.0}
    return sample_vars(datetime.now(), loc["lat"], loc["lon"], prev=prev)

# ============ 天气 → 天空色调联动 ============
# 让画面语义与天气胶囊一致：阴/雨/雪/雾时把天空向灰蓝压暗，避免“阴天却亮蓝”的违和。
# 权重保守（0.18~0.4），保留昼夜明暗层次。


def weather_tint(v: dict, kind: str) -> dict:
    """按天气对天空三色施加灰调（原地返回新 dict）。"""
    weights = {
        "cloudy": 0.20,
        "fog": 0.26,
        "rain": 0.30,
        "heavy_rain": 0.36,
        "storm": 0.40,
        "snow": 0.14,
    }
    w = weights.get(kind, 0.0)
    if w <= 0:
        return v
    tint = "#4E5A6B"
    out = dict(v)
    # 地平线暖带在坏天气下压得更狠，防止“黄昏金带出现在雨夜”
    out["sky_top"] = mix_hex(v["sky_top"], tint, w * 0.9)
    out["sky_mid"] = mix_hex(v["sky_mid"], tint, w)
    out["sky_hor"] = mix_hex(v["sky_hor"], tint, min(1.0, w * 1.6))
    return out
