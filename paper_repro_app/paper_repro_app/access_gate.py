# -*- coding: utf-8 -*-
"""远程访问口令门 + 受信设备令牌（mobile_trust 规范 v1.0 P0）。

口令只在 expose 模式（lan/tunnel）启用；PBKDF2 加盐哈希存本机；
受信设备：口令通过后可签发 URL 设备令牌（?tk=…），本机只存 sha256；
epoch 全局作废（改口令/整体吊销即 +1）；逐条可吊销；TTL 默认 180 天。
通过后写 session（app 层）。失败固定文案；不落日志。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

ACCESS_FILE = Path.home() / ".paper_repro_app" / "access.json"
_ITERATIONS = 200_000
_DEFAULT_TTL_DAYS = 180
_LOCK = threading.Lock()


def _ttl_days() -> int:
    try:
        return max(0, int(os.environ.get("PAPER_REPRO_TRUST_TTL_DAYS", _DEFAULT_TTL_DAYS)))
    except ValueError:
        return _DEFAULT_TTL_DAYS


def _read() -> dict:
    try:
        data = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("salt") and data.get("hash"):
            data.setdefault("epoch", 1)
            data.setdefault("tokens", [])
            return data
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _write(data: dict) -> bool:
    try:
        ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCESS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(ACCESS_FILE, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False


def is_configured() -> bool:
    return bool(_read())


def set_access_code(code: str) -> bool:
    """设置访问口令（成功即 epoch+1：此前签发的受信令牌全部作废）。"""
    code = (code or "").strip()
    if len(code) < 4:
        return False
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS).hex()
    data = {"salt": salt, "hash": digest, "epoch": 1, "tokens": []}
    if not _write(data):
        return False
    return True


def verify_access_code(code: str) -> bool:
    rec = _read()
    if not rec:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", (code or "").encode("utf-8"),
                                 bytes.fromhex(rec["salt"]), _ITERATIONS).hex()
    return hmac.compare_digest(digest, rec["hash"])


def clear_access_code() -> bool:
    try:
        if ACCESS_FILE.exists():
            ACCESS_FILE.unlink()
        return True
    except OSError:
        return False


# ---------- 受信设备令牌 ----------

def issue_device_token(name: str = "手机") -> str:
    """签发设备令牌：返回明文（仅此一次可见）；本机只存 sha256。"""
    rec = _read()
    if not rec:
        return ""
    raw = secrets.token_urlsafe(32)
    now = int(time.time())
    ttl_days = _ttl_days()
    with _LOCK:
        rec = _read()
        rec.setdefault("tokens", [])
        rec.setdefault("epoch", 1)
        rec["tokens"] = [t for t in rec.get("tokens", []) if t.get("expires_at", now + 1) > now]
        rec["tokens"].append({
            "id": secrets.token_hex(6),
            "name": (name or "设备")[:20],
            "hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "created_at": now,
            "expires_at": now + ttl_days * 86400 if ttl_days else 0,
            "last_used_at": now,
        })
        _write(rec)
    return raw


def verify_device_token(raw: str) -> bool:
    """校验设备令牌；命中更新 last_used_at（分钟节流）。失败与口令失败同静默。"""
    if not raw:
        return False
    rec = _read()
    if not rec:
        return False
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = int(time.time())
    with _LOCK:
        rec = _read()
        rec.setdefault("tokens", [])
        rec.setdefault("epoch", 1)
        for token in rec["tokens"]:
            if not hmac.compare_digest(token.get("hash", ""), digest):
                continue
            if token.get("expires_at") and token["expires_at"] < now:
                return False
            if now - int(token.get("last_used_at") or 0) > 60:
                token["last_used_at"] = now
                _write(rec)
            return True
    return False


def list_device_tokens() -> list:
    rec = _read()
    now = int(time.time())
    return [t for t in rec.get("tokens", []) if not (t.get("expires_at") and t["expires_at"] < now)]


def revoke_device_token(token_id: str) -> bool:
    with _LOCK:
        rec = _read()
        before = len(rec.get("tokens", []))
        rec["tokens"] = [t for t in rec.get("tokens", []) if t.get("id") != token_id]
        if len(rec["tokens"]) != before:
            _write(rec)
            return True
    return False


def revoke_all_tokens() -> bool:
    """整体吊销：epoch+1（旧令牌全部失效）并清表。"""
    with _LOCK:
        rec = _read()
        rec["epoch"] = int(rec.get("epoch", 1)) + 1
        rec["tokens"] = []
        return _write(rec)
