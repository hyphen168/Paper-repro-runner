# -*- coding: utf-8 -*-
"""AI 助手 · OpenAI 兼容网关（ai_assistant 规范 v1.0）

零新依赖：requests 流式手解析 SSE；纯逻辑零 streamlit。
安全：发送前统一 sanitize_for_llm；云端无 Key；Key 原文断言拒发。
"""
from __future__ import annotations

import json
import re
from typing import Callable, Dict, List, Optional

import requests

PROVIDERS = {
    "DeepSeek": {"base_url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-reasoner"]},
    "Moonshot Kimi": {"base_url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
    "通义 Qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": ["qwen-plus", "qwen-turbo", "qwen-max"]},
    "智谱 GLM": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"]},
    "OpenAI": {"base_url": "https://api.openai.com/v1", "models": ["gpt-4o-mini", "gpt-4o"]},
}
DEFAULT_PROVIDER = "DeepSeek"
# 发送前清洗：剥离疑似凭据/签名 token
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_BEARER_PATTERN = re.compile(r"\b(Bearer|Authorization)\s+[A-Za-z0-9._~+/=-]{12,}", re.I)
_SIGNED_PATTERN = re.compile(r"([?&](?:X-Amz-[A-Za-z0-9-]+|Signature|sig|token|key|api[_-]?key))=[^&\s\"']{8,}", re.I)
_KEY_QUERY_PATTERN = re.compile(r"[?&](?:api[_-]?key|access[_-]?token)=[^&\s\"']+")


def sanitize_for_llm(text: str) -> str:
    """扩展脱敏：PEM/password（复用 ssh_utils.sanitize）+ sk-/Bearer/签名 token/密钥参数。"""
    if not text:
        return text or ""
    out = str(text)
    try:
        from paper_repro_app.ssh_utils import sanitize as _base_sanitize
        out = _base_sanitize(out)
    except ImportError:
        pass
    out = _SK_PATTERN.sub("sk-<redacted>", out)
    out = _BEARER_PATTERN.sub(r"\1 <redacted>", out)
    out = _SIGNED_PATTERN.sub(r"\1=<redacted>", out)
    out = _KEY_QUERY_PATTERN.sub("&<redacted>", out)
    return out


def estimate_tokens(text: str) -> int:
    """粗略估算（中文≈1.6 token/字，西文≈0.4/字符），用于截断决策。"""
    zh = sum(1 for ch in text if ord(ch) > 0x2E80)
    return int(zh * 1.6 + (len(text) - zh) * 0.4)


def _headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _parse_sse_line(line: str) -> Optional[str]:
    """解析一条 SSE 文本行：返回 delta 文本或 None。"""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
        choices = obj.get("choices") or []
        if not choices:
            return None
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""
    except (ValueError, TypeError):
        return None


def list_models(base_url: str, api_key: str, timeout=(10, 30)) -> tuple:
    """GET /models 探测；404/405 降级一次 chat 探活。返回 (ok, msg, ids)。"""
    url = base_url.rstrip("/") + "/models"
    try:
        resp = requests.get(url, headers=_headers(api_key), timeout=timeout)
        if resp.status_code in (200, 201):
            ids = [m.get("id") for m in (resp.json().get("data") or []) if isinstance(m, dict) and m.get("id")]
            return True, f"连接成功，可用模型 {len(ids)} 个。", ids[:80]
        if resp.status_code in (401, 403):
            return False, "认证失败：API Key 无效或无权限（HTTP %s）。" % resp.status_code, []
        if resp.status_code in (404, 405):
            ok, msg, _ = chat_once([{"role": "user", "content": "hi"}], base_url, api_key, "gpt-4o-mini", max_tokens=1)
            if ok:
                return True, "端点不支持 /models，但对话接口可用。", []
            return False, msg, []
        return False, "模型列表查询失败（HTTP %s）：%s" % (resp.status_code, resp.text[:200]), []
    except requests.RequestException as exc:
        return False, "网络错误：%s" % str(exc)[:160], []


def chat_once(messages: List[Dict[str, str]], base_url: str, api_key: str,
              model: str, max_tokens: int = 1200, timeout=(15, 150)) -> tuple:
    """非流式单轮。返回 (ok, text|err)。"""
    url = base_url.rstrip("/") + "/chat/completions"
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    try:
        resp = requests.post(url, headers=_headers(api_key), json=body, timeout=timeout)
        if resp.status_code != 200:
            return False, "接口错误（HTTP %s）：%s" % (resp.status_code, resp.text[:240])
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
        return True, content
    except requests.RequestException as exc:
        return False, "网络错误：%s" % str(exc)[:160]


def chat_stream(messages: List[Dict[str, str]], base_url: str, api_key: str,
                model: str, on_delta: Callable[[str], None],
                max_tokens: int = 1200, timeout=(15, 150)) -> tuple:
    """流式对话：SSE 手解析，on_delta 收增量。返回 (ok, 完整文本|错误)。"""
    url = base_url.rstrip("/") + "/chat/completions"
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "stream": True}
    collected: List[str] = []
    try:
        with requests.post(url, headers=_headers(api_key), json=body, stream=True, timeout=timeout) as resp:
            if resp.status_code != 200:
                return False, "接口错误（HTTP %s）：%s" % (resp.status_code, resp.text[:240])
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                delta = _parse_sse_line(raw_line)
                if delta is None:
                    if raw_line.strip() == "data: [DONE]":
                        break
                    continue
                if delta:
                    collected.append(delta)
                    try:
                        on_delta(delta)
                    except Exception:
                        pass
        return True, "".join(collected)
    except requests.RequestException as exc:
        return False, "网络错误：%s" % str(exc)[:160]


def assert_no_key_leak(text: str, api_key: str) -> bool:
    """发送/命令生成前断言不含 Key 原文。"""
    return not api_key or api_key not in text
