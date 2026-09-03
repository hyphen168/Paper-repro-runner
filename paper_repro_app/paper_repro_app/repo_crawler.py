from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List
import requests
from bs4 import BeautifulSoup

try:
    from paper_repro_app.logging_config import get_logger
    logger = get_logger("repo_crawler")
except ImportError:
    import logging
    logger = logging.getLogger("repo_crawler")


class AutoRepoDatasetCrawler:
    """Crawler engine to discover, evaluate, and rank candidate code repositories and datasets for paper reproduction."""

    def __init__(self, timeout: int = 12):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def extract_keywords_from_paper(self, paper_url: str) -> List[str]:
        """Extract key search terms (title, subject) from a paper link (arXiv, PapersWithCode, DOI)."""
        keywords = []
        if not paper_url:
            return keywords

        # Extract paper ID or URL tokens
        clean_url = paper_url.strip()
        arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", clean_url, re.IGNORECASE)
        
        try:
            resp = self.session.get(clean_url, timeout=self.timeout)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Title parsing
                title_tag = soup.find("h1", class_="title") or soup.find("title")
                if title_tag:
                    title = title_tag.get_text().replace("Title:", "").strip()
                    # Clean title
                    title = re.sub(r"\[.*?\]", "", title).strip()
                    keywords.append(title)
        except Exception as e:
            logger.warning(f"解析论文标题失败 ({clean_url}): {e}")

        if arxiv_match:
            keywords.append(arxiv_match.group(1))

        return [kw for kw in keywords if kw]

    def search_github_candidates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search GitHub search API or HTML for top repository candidates."""
        candidates = []
        if not query:
            return candidates

        clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
        search_url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(clean_query)}&sort=stars&order=desc&per_page={limit}"

        try:
            resp = self.session.get(search_url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    candidates.append({
                        "name": item.get("full_name"),
                        "repo_url": item.get("html_url"),
                        "clone_url": item.get("clone_url"),
                        "stars": item.get("stargazers_count", 0),
                        "forks": item.get("forks_count", 0),
                        "description": item.get("description") or "",
                        "updated_at": item.get("updated_at") or "",
                        "source": "github_api",
                        "score": item.get("stargazers_count", 0) + item.get("forks_count", 0) * 2,
                    })
        except Exception as e:
            logger.warning(f"GitHub API 搜索失败: {e}")

        return candidates

    def search_gitee_candidates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Gitee open source repositories for fast domestic cloning."""
        candidates = []
        if not query:
            return candidates

        clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
        search_url = f"https://gitee.com/api/v5/search/repositories?q={urllib.parse.quote(clean_query)}&order=desc&page=1&per_page={limit}"

        try:
            resp = self.session.get(search_url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for item in data:
                        candidates.append({
                            "name": item.get("path_with_namespace"),
                            "repo_url": item.get("html_url"),
                            "clone_url": item.get("html_url") + ".git",
                            "stars": item.get("stargazers_count", 0),
                            "forks": item.get("forks_count", 0),
                            "description": item.get("description") or "",
                            "updated_at": item.get("updated_at") or "",
                            "source": "gitee_api",
                            "score": (item.get("stargazers_count", 0) + item.get("forks_count", 0) * 2) + 500, # Priority for fast domestic access
                        })
        except Exception as e:
            logger.warning(f"Gitee API 搜索失败: {e}")

        return candidates

    def evaluate_and_rank_candidates(
        self, paper_url: str, user_repo_hint: str = ""
    ) -> Dict[str, Any]:
        """Automatically crawl and rank candidate repos and dataset mirrors."""
        all_candidates: List[Dict[str, Any]] = []

        # 1. If explicit user hint provided, give highest priority (unless it's a dummy placeholder)
        if user_repo_hint.strip() and "your-username" not in user_repo_hint:
            hint_url = user_repo_hint.strip()
            # Generate accelerated clone mirrors
            gh_proxy = f"https://ghfast.top/{hint_url}" if "github.com" in hint_url else hint_url
            all_candidates.append({
                "name": "用户指定仓库",
                "repo_url": hint_url,
                "clone_url": gh_proxy,
                "stars": 9999,
                "forks": 9999,
                "description": "用户手动填写的优选仓库地址",
                "source": "user_input",
                "score": 10000,
            })

        # 2. Extract title & keywords
        keywords = self.extract_keywords_from_paper(paper_url)
        search_query = keywords[0] if keywords else ""

        # 3. Crawl GitHub and Gitee
        gh_results = self.search_github_candidates(search_query, limit=5)
        gt_results = self.search_gitee_candidates(search_query, limit=5)

        for item in gh_results + gt_results:
            # Add accelerated clone mirror for GitHub
            if "github.com" in item["repo_url"] and not item.get("accelerated_url"):
                item["accelerated_url"] = f"https://ghfast.top/{item['repo_url']}"
            all_candidates.append(item)

        # 4. Sort by score descending
        all_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        best_candidate = all_candidates[0] if all_candidates else None

        dataset_info = {
            "name": "待从目标仓库配置中识别",
            "detected": False,
            "mirror_download_url": "",
            "instructions": "云端会扫描目标仓库的数据集配置；只有 YAML 声明官方下载地址时才会自动下载并校验。",
        }

        return {
            "query_used": search_query,
            "best_candidate": best_candidate,
            "candidate_list": all_candidates,
            "dataset_info": dataset_info,
        }
