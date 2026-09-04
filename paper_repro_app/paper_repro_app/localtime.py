"""当地时刻服务：以「天气位置」的当地墙上时钟为基准，供昼夜/时钟显示使用。

背景：昼夜系统（day_night）此前用机器本机时区（time.localtime().tm_gmtoff）换算 UTC；
当天气位置（IP 定位或手动城市经纬度）与机器时区不一致时，用户希望按「当地真实时刻」
而不是机器时区时间驱动昼夜与时钟展示。

数据来源优先级：
- utc_offset_seconds：Open-Meteo（timezone=auto）返回并缓存在 weather_cache.json 的当地偏移；
- 经度近似：lon/15° = 1 小时（缓存缺失偏移键时兜底）；
- 本机时区 / 0：全部不可用时最终兜底。

零第三方依赖、零 UI 依赖（可纯单测）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from paper_repro_app.paths import APP_HOME

# 与 weather_fx._write_cache 相同的缓存文件
WEATHER_CACHE_FILE = APP_HOME / "weather_cache.json"

# Open-Meteo 合法当地偏移范围（UTC-12 .. UTC+14）
_MIN_OFFSET_S = -12 * 3600
_MAX_OFFSET_S = 14 * 3600


def _read_weather_cache() -> Optional[dict]:
    """读天气缓存 JSON；文件缺失/损坏返回 None。"""
    try:
        if not WEATHER_CACHE_FILE.exists():
            return None
        data = json.loads(WEATHER_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return None


def lon_offset_seconds(lon) -> int:
    """按经度近似当地时区偏移（每 15° = 1 小时）。非法输入返回 0。"""
    try:
        return int(round(float(lon) / 15.0) * 3600)
    except (TypeError, ValueError):
        return 0


def _validate_offset(raw) -> Optional[int]:
    """把任意取值规范化为秒级偏移；非数字/越界返回 None。"""
    try:
        offset = int(raw)
    except (TypeError, ValueError):
        return None
    if _MIN_OFFSET_S <= offset <= _MAX_OFFSET_S:
        return offset
    return None


def get_location_offset_seconds() -> Optional[int]:
    """读天气缓存/天气数据得当地 utc_offset_seconds（秒）；不可用返回 None。

    旧缓存缺偏移键时按 lon 经度近似补上（比回落本机时区更贴近“当地”）。
    """
    data = _read_weather_cache()
    if not data:
        return None
    raw = data.get("utc_offset_seconds")
    if raw is None:
        lon = data.get("lon")
        if lon is None:
            return None
        raw = lon_offset_seconds(lon)
    return _validate_offset(raw)


def location_utc_offset_seconds() -> int:
    """确定性兜底偏移：缓存当地偏移 → 经度近似 → 本机时区偏移 → 0。"""
    cached = get_location_offset_seconds()
    if cached is not None:
        return cached
    try:
        offset = datetime.now(timezone.utc).astimezone().utcoffset()
        if offset is not None:
            return int(offset.total_seconds())
    except Exception:
        pass
    return 0


def location_now() -> datetime:
    """返回「天气位置当地墙上时钟」的 naive datetime。

    当地偏移未知时回落本机当前时刻（datetime.now()）。
    """
    offset = get_location_offset_seconds()
    if offset is None:
        return datetime.now()
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset)


def format_hhmm(dt: Optional[datetime] = None) -> str:
    """把时刻格式化为 HH:MM；dt 为空时取当地时刻。"""
    if dt is None:
        dt = location_now()
    return dt.strftime("%H:%M")
