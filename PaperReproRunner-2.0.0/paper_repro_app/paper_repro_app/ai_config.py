# -*- coding: utf-8 -*-
"""AI 助手 · 凭据与配置存储（ai_assistant 规范 v1.0）

Windows 用 DPAPI（stdlib ctypes → crypt32）加密存本机；非 Windows 回落明文 0600。
独立文件（不复用 cloud_config.json，防整体覆盖误删）。Key 不进日志/DB/任务/云机。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

CRED_DIR = Path.home() / ".paper_repro_app"
CRED_FILE = CRED_DIR / "llm_credentials.bin"
_LOCK = threading.Lock()
_IS_WINDOWS = sys.platform == "win32"

# ---- DPAPI（仅 Windows）----


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(blob_in: bytes, encrypt: bool) -> Optional[bytes]:
    try:
        crypt32 = ctypes.windll.crypt32
        in_blob = _DATA_BLOB(len(blob_in), ctypes.cast(ctypes.create_string_buffer(blob_in), ctypes.POINTER(ctypes.c_char)))
        out_blob = _DATA_BLOB()
        ok = crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)) if encrypt \
            else crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return None
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return raw
    except Exception:
        return None


def _encrypt(plain: str) -> bytes:
    data = plain.encode("utf-8")
    if _IS_WINDOWS:
        encrypted = _dpapi(data, True)
        if encrypted is not None:
            return encrypted
    return data  # fallback：明文（非 Windows 靠文件权限）


def _decrypt(blob: bytes) -> Optional[str]:
    if _IS_WINDOWS:
        plain = _dpapi(blob, False)
        if plain is not None:
            return plain.decode("utf-8", errors="replace")
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---- 读写 ----

def save_credentials(config: Dict[str, Any]) -> bool:
    """config: {provider, base_url, api_key, model, tested_at}。api_key 可为空=仅更新其它字段。"""
    with _LOCK:
        existing = load_credentials()
        merged = dict(existing)
        merged.update({k: v for k, v in config.items() if v not in (None, "")})
        api_key = merged.get("api_key") or ""
        try:
            CRED_DIR.mkdir(parents=True, exist_ok=True)
            CRED_FILE.write_bytes(_encrypt(api_key))
            # 元数据（不含 key）单独明文存便于快速读取
            merged.setdefault("thinking", "standard")
            meta = {k: v for k, v in merged.items() if k != "api_key"}
            meta_path = CRED_DIR / "llm_meta.json"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            try:
                os.chmod(CRED_FILE, 0o600)
                os.chmod(meta_path, 0o600)
            except OSError:
                pass
            return True
        except OSError:
            return False


def load_credentials() -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    try:
        meta_path = CRED_DIR / "llm_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        meta = {}
    api_key = ""
    if CRED_FILE.exists():
        try:
            plain = _decrypt(CRED_FILE.read_bytes())
            if plain:
                api_key = plain
        except OSError:
            pass
    meta["api_key"] = api_key
    return meta


def clear_credentials() -> bool:
    ok = True
    for path in (CRED_FILE, CRED_DIR / "llm_meta.json"):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            ok = False
    return ok


def api_key_tail(api_key: str) -> str:
    return ("…" + api_key[-4:]) if len(api_key) > 4 else ""
