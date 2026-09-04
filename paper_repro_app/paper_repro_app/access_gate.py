# -*- coding: utf-8 -*-
"""远程访问口令门（mobile_access 规范 P0）。

口令只在 expose 模式（lan/tunnel）启用；PBKDF2 加盐哈希存本机；
通过后写 session（app 层）；失败固定文案+退避提示；不落日志。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

ACCESS_FILE = Path.home() / ".paper_repro_app" / "access.json"
_ITERATIONS = 200_000


def _read() -> dict:
    try:
        data = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("salt") and data.get("hash"):
            return data
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def is_configured() -> bool:
    return bool(_read())


def set_access_code(code: str) -> bool:
    """首次设置访问口令（expose 模式启动但无口令时引导设置）。"""
    code = (code or "").strip()
    if len(code) < 4:
        return False
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS).hex()
    try:
        ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCESS_FILE.write_text(json.dumps({"salt": salt, "hash": digest}), encoding="utf-8")
        try:
            os.chmod(ACCESS_FILE, 0o600)
        except OSError:
            pass
        return True
    except OSError:
        return False


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
