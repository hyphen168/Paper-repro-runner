# -*- coding: utf-8 -*-
"""仓库档案记忆（paper_switch 规范）：repo_profiles.json 的读写与预填查询。

安全红线：不写密码/私钥/日志原文；host 只记主机名；认证只记类型枚举。
DB 是史实源，本文件是可重建物化视图（rebuild_profiles_from_db 显式重建）。
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

PROFILE_DIR = Path.home() / ".paper_repro_app"
PROFILE_FILE = PROFILE_DIR / "repo_profiles.json"
_LOCK = threading.Lock()

_SCHEMA = {"schema_version": 1, "updated_at": "", "profiles": {}}

_ACCEL_PREFIXES = ("https://ghfast.top/https://", "https://ghproxy.com/https://",
                   "https://mirror.ghproxy.com/https://", "https://gh-proxy.com/https://")


def normalize_repo_url(url: str) -> str:
    """键规范化：去加速前缀/.git/尾斜杠；ssh/git@ 转 https；统一小写主机。"""
    value = (url or "").strip()
    for prefix in _ACCEL_PREFIXES:
        if value.startswith(prefix):
            value = "https://" + value[len(prefix):]
            break
    m = re.match(r"^(?:git@|ssh://)([^/:]+)[:/](.+)$", value)
    if m:
        value = "https://" + m.group(1) + "/" + m.group(2)
    value = re.sub(r"^http://", "https://", value)
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def _read_raw() -> Dict[str, Any]:
    if not PROFILE_FILE.exists():
        return {"schema_version": 1, "updated_at": "", "profiles": {}}
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
            raise ValueError("profiles 结构缺失")
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        # 损坏文件改名保留，空档启动
        try:
            PROFILE_FILE.replace(PROFILE_FILE.with_suffix(".corrupt"))
        except OSError:
            pass
        return {"schema_version": 1, "updated_at": "", "profiles": {}}


def _save_atomic(data: Dict[str, Any]) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROFILE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, PROFILE_FILE)
    try:
        os.chmod(PROFILE_FILE, 0o600)
    except OSError:
        pass


def load_profiles() -> Dict[str, Any]:
    with _LOCK:
        return _read_raw()


def get_for_repo(repo_url: str) -> Optional[Dict[str, Any]]:
    """按规范化键（含别名三段匹配）取档案；无档案返回 None。"""
    key = normalize_repo_url(repo_url)
    if not key:
        return None
    data = _read_raw()
    profiles = data.get("profiles", {})
    if key in profiles:
        return profiles[key]
    # 别名匹配：owner/name 三段（大小写不敏感）
    m = re.search(r"([^/]+)/([^/]+)$", key)
    if m:
        owner, name = m.group(1).lower(), m.group(2).lower()
        for cand_key, cand in profiles.items():
            cm = re.search(r"([^/]+)/([^/]+)$", cand_key)
            if cm and cm.group(1).lower() == owner and cm.group(2).lower() == name:
                return cand
    return None


def upsert_profile(repo_url: str, patch: Dict[str, Any]) -> None:
    """合并写入档案（失败只记标签与建议；成功字段绝不因失败覆盖）。"""
    key = normalize_repo_url(repo_url)
    if not key:
        return
    with _LOCK:
        data = _read_raw()
        profiles = data.setdefault("profiles", {})
        entry = profiles.get(key) or {"repo": key, "run_count": 0, "success_count": 0,
                                      "fail_reason_tags": [], "aliases": []}
        prev_status = entry.get("last_status")
        entry["last_attempt_at"] = datetime.now().isoformat(timespec="seconds")
        entry["run_count"] = int(entry.get("run_count") or 0) + 1
        if patch.get("status") == "success":
            for field in ("entrypoint", "run_command", "data_config", "env_note",
                          "task_family", "mode", "host_hint"):
                if field in patch and patch[field] not in (None, ""):
                    entry[field] = patch[field]
            entry["last_status"] = "success"
            entry["last_success_at"] = entry["last_attempt_at"]
            entry["success_count"] = int(entry.get("success_count") or 0) + 1
        else:
            tag = patch.get("fail_tag") or ""
            if tag and tag not in entry.setdefault("fail_reason_tags", []):
                entry["fail_reason_tags"].append(tag)
            if prev_status != "success":
                entry["last_status"] = patch.get("status") or "failed"
        entry.setdefault("aliases", [])
        alias = patch.get("alias") or ""
        if alias and alias not in entry["aliases"]:
            entry["aliases"].append(alias)
        profiles[key] = entry
        _save_atomic(data)


def remove_profile(repo_url: str) -> bool:
    key = normalize_repo_url(repo_url)
    with _LOCK:
        data = _read_raw()
        if key in data.get("profiles", {}):
            del data["profiles"][key]
            _save_atomic(data)
            return True
    return False


def list_profiles() -> list:
    data = _read_raw()
    return sorted(data.get("profiles", {}).values(),
                  key=lambda e: e.get("last_attempt_at") or "", reverse=True)


def rebuild_profiles_from_db(db_tasks) -> int:
    """从任务历史（list 每项含 repo_url/run_command/data_config/status/current_step/log…）重建档案。显式调用。"""
    counter = 0
    with _LOCK:
        data = _read_raw()
        profiles = data.setdefault("profiles", {})
        for task in db_tasks:
            repo = task.get("repo_url") or ""
            if not repo:
                continue
            key = normalize_repo_url(repo)
            entry = profiles.setdefault(key, {"repo": key, "run_count": 0, "success_count": 0,
                                              "fail_reason_tags": [], "aliases": []})
            status = str(task.get("status") or "").lower()
            entry["run_count"] = int(entry.get("run_count") or 0) + 1
            if status == "success":
                if task.get("run_command"):
                    entry["run_command"] = task["run_command"]
                if task.get("data_config"):
                    entry["data_config"] = task["data_config"]
                entry["last_status"] = "success"
                entry["last_success_at"] = datetime.now().isoformat(timespec="seconds")
                entry["success_count"] = int(entry.get("success_count") or 0) + 1
            elif status in ("failed", "cancelled") and entry.get("last_status") != "success":
                entry["last_status"] = status
            entry["last_attempt_at"] = datetime.now().isoformat(timespec="seconds")
            counter += 1
        _save_atomic(data)
    return counter
