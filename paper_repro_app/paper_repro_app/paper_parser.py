from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# 代码托管平台（模型仓库首页 huggingface.co/{owner}/{repo} 也计入）
_REPO_HOSTS = {"github.com", "gitlab.com", "gitee.com", "huggingface.co"}
# 平台自身“非仓库”一级目录（docs/blog/explore 等），命中的页面不是代码仓库
_RESERVED_TOP = {
    "docs", "blog", "learn", "explore", "topics", "about", "pricing", "login",
    "signin", "sign-in", "signup", "sign-up", "logout", "join", "settings",
    "organizations", "orgs", "sponsors", "marketplace", "collections",
    "trending", "features", "customers", "enterprise", "security", "contact",
    "site", "readme", "notifications", "new", "search", "events", "pulls",
    "issues", "actions", "packages", "projects", "teams", "view", "apps",
    "models", "datasets", "spaces", "papers", "tasks", "community", "hardware",
    "hub", "forgot-password", "profile", "posts", "conversations", "help",
    "users", "usage", "api", "graphql", "open-source", "insights",
}
# huggingface 第二级也绝不能是文档/入口页
_HF_RESERVED_SECOND = {"docs", "blog", "about", "datasets", "models", "spaces", "tasks", "learn", "pricing", "login"}


def normalize_repo_url(url: str) -> str:
    if not url:
        return ""
    return url.strip().rstrip("/")


def looks_like_repo_url(url: str) -> bool:
    """判断 URL 是否真的是「代码/模型仓库主页或其文件页」，排除文档/个人主页等。"""
    url = normalize_repo_url(url or "")
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    if host not in _REPO_HOSTS:
        return False
    segs = [p for p in (parsed.path or "").split("/") if p]
    if len(segs) < 2:
        return False  # 个人主页 / 平台首页都不算仓库
    owner = segs[0].lower()
    if owner in _RESERVED_TOP:
        return False
    if host == "huggingface.co":
        repo = segs[1].lower()
        if repo in _HF_RESERVED_SECOND:
            return False
        # 允许文件页（/resolve/… 等），但至少 owner/repo 两段
        return True
    # github/gitlab/gitee：owner/repo，第三段可为 tree/blob/releases 等文件浏览
    return True


def _iter_repo_candidates(soup: BeautifulSoup, html: str):
    """按文档出现顺序产出候选链接（去重），先 anchor 后裸正则。"""
    seen = set()
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "")
        if any(h in href for h in _REPO_HOSTS):
            if href not in seen:
                seen.add(href)
                yield href
    pattern = re.compile(r"https?://(?:%s)[^\s\"'<>]+" % "|".join(_REPO_HOSTS))
    for m in pattern.finditer(html):
        u = m.group(0)
        if u not in seen:
            seen.add(u)
            yield u


def extract_repo_url(paper_url: str) -> Optional[str]:
    """从论文页面推断代码仓库：只接受「真仓库形态」链接（自动忽略 HF 文档页等）。"""
    if not paper_url or not str(paper_url).strip().lower().startswith(("http://", "https://")):
        return None
    try:
        response = requests.get(paper_url.strip(), timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        return None

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    for candidate in _iter_repo_candidates(soup, html):
        normalized = normalize_repo_url(candidate)
        if normalized and looks_like_repo_url(normalized):
            return normalized
    return None


def extract_paper_metadata(paper_url: str) -> Dict[str, str]:
    metadata = {"title": "", "repo_url": ""}
    if not paper_url or not str(paper_url).strip().lower().startswith(("http://", "https://")):
        return metadata
    try:
        response = requests.get(paper_url, timeout=8)
        response.raise_for_status()
    except requests.RequestException:
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.title
    if title_tag:
        metadata["title"] = title_tag.get_text(" ", strip=True)
    metadata["repo_url"] = extract_repo_url(paper_url) or ""
    return metadata
