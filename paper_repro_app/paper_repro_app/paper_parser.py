from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def normalize_repo_url(url: str) -> str:
    if not url:
        return ""
    return url.strip().rstrip("/")


def extract_repo_url(paper_url: str) -> Optional[str]:
    """Try to infer a repository URL from a paper URL or abstract page."""
    if not paper_url:
        return None
    try:
        response = requests.get(paper_url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    candidates = set()

    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "")
        if "github.com" in href or "gitlab.com" in href or "huggingface.co" in href:
            candidates.add(href)

    for candidate in candidates:
        normalized = normalize_repo_url(candidate)
        if normalized and ("github.com" in normalized or "gitlab.com" in normalized or "huggingface.co" in normalized):
            return normalized

    match = re.search(r"https?://(?:github\.com|gitlab\.com|huggingface\.co)[^\s\"'<>]+", html)
    if match:
        return normalize_repo_url(match.group(0))

    return None


def extract_paper_metadata(paper_url: str) -> Dict[str, str]:
    metadata = {"title": "", "repo_url": ""}
    try:
        response = requests.get(paper_url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")
    title_tag = soup.title
    if title_tag:
        metadata["title"] = title_tag.get_text(" ", strip=True)
    metadata["repo_url"] = extract_repo_url(paper_url) or ""
    return metadata
