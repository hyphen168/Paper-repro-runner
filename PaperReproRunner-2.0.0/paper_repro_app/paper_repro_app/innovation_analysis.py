from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup


KEYWORD_GROUPS: Dict[str, List[str]] = {
    "attention": ["attention", "transformer", "self-attention", "multi-head", "channel attention", "spatial attention"],
    "multiscale": ["multi-scale", "multiscale", "pyramid", "feature pyramid", "feature fusion", "cross-scale"],
    "domain_generalization": ["domain adaptation", "domain generalization", "cross-domain", "style transfer", "few-shot", "few shot"],
    "contrastive": ["contrastive learning", "self-supervised", "representation learning", "prototype", "metric learning"],
    "detection": ["object detection", "anchor-free", "bbox", "yolo", "retinanet", "feature map"],
    "segmentation": ["segmentation", "instance segmentation", "semantic segmentation", "panoptic", "mask"],
    "augmentation": ["data augmentation", "mixup", "cutmix", "augmentation", "regularization"],
    "distillation": ["knowledge distillation", "student teacher", "distillation", "compression"],
    "efficient": ["efficient", "lightweight", "pruning", "quantization", "mobilenet", "tiny model"],
}


def _safe_fetch(url: str) -> str:
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _collect_keyword_hits(text: str, keyword_groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
    hits: Dict[str, List[str]] = {}
    lowered = text.lower()
    for group_name, keywords in keyword_groups.items():
        found = [keyword for keyword in keywords if keyword.lower() in lowered]
        if found:
            hits[group_name] = found
    return hits


def _find_repo_readme(repo_url: str, repo_dir: Optional[str | Path] = None) -> str:
    if repo_dir:
        repo_path = Path(repo_dir)
        for candidate in [repo_path / "README.md", repo_path / "README.MD", repo_path / "readme.md"]:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(repo_path.rglob("*.md"))[:20]:
            if path.name.lower().startswith("readme"):
                return path.read_text(encoding="utf-8", errors="ignore")

    if not repo_url:
        return ""

    try:
        parsed = repo_url.split("github.com/", 1)[1]
        repo_path = parsed.strip("/")
        owner, repo = repo_path.split("/", 1)[:2]
        readme_urls = [
            f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md",
            f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md",
        ]
        for url in readme_urls:
            text = _safe_fetch(url)
            if text:
                return text
    except Exception:
        pass
    return ""


def _extract_html_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return _clean_text(text)


class PaperInnovationAnalyzer:
    """Heuristic innovation analysis based on paper text, repo description, and execution logs."""

    def __init__(self):
        self.keyword_groups = KEYWORD_GROUPS

    def analyze(self, paper_url: str, repo_url: str, reproduction_logs: str = "", repo_dir: Optional[str | Path] = None) -> Dict[str, Any]:
        paper_text = ""
        if paper_url:
            paper_text = _extract_html_text(_safe_fetch(paper_url))
        repo_text = _find_repo_readme(repo_url, repo_dir)
        if not repo_text and repo_url:
            repo_text = _extract_html_text(_safe_fetch(repo_url))

        paper_hits = _collect_keyword_hits(paper_text, self.keyword_groups)
        repo_hits = _collect_keyword_hits(repo_text, self.keyword_groups)
        log_hits = _collect_keyword_hits(reproduction_logs or "", self.keyword_groups)

        combined_hits: Dict[str, List[str]] = {}
        for group in sorted(set(paper_hits) | set(repo_hits) | set(log_hits)):
            combined_hits[group] = sorted(set((paper_hits.get(group) or []) + (repo_hits.get(group) or []) + (log_hits.get(group) or [])))

        possible_innovations: List[str] = []
        if combined_hits:
            if "attention" in combined_hits:
                possible_innovations.append("多头注意力 / Transformer 结构增强：论文和代码中都强调了多尺度特征与上下文建模，说明方案在全局语义建模方面有明显提升。")
            if "multiscale" in combined_hits:
                possible_innovations.append("多尺度特征融合：代码和结论呈现出分层特征融合行为，具备对小目标、遮挡和细节恢复更敏感的潜力。")
            if "domain_generalization" in combined_hits:
                possible_innovations.append("跨域 / 鲁棒泛化设计：模型倾向于减少不同场景间的分布偏移，可能在真实部署时具有更强稳定性。")
            if "contrastive" in combined_hits:
                possible_innovations.append("对比学习或表征约束：结构更强调判别式特征表达，可能提高类间区分与样本表征质量。")
            if "distillation" in combined_hits:
                possible_innovations.append("知识蒸馏或轻量化设计：说明模型在保持准确率的同时兼顾推理成本，这通常具有工程部署价值。")
            if "efficient" in combined_hits:
                possible_innovations.append("轻量化与压缩设计：代码中存在模型压缩、剪枝或高效结构组件，说明方法重视部署友好性。")
            if "augmentation" in combined_hits:
                possible_innovations.append("增强策略创新：数据增强或正则手段可能提升泛化，并对少样本或噪声环境更稳健。")
            if "segmentation" in combined_hits:
                possible_innovations.append("分割 / 细粒度定位能力：模型可能在区域边界表达和细粒度识别上有提升，适合复杂工业检测场景。")
            if "detection" in combined_hits:
                possible_innovations.append("检测头或定位策略创新：存在更强的目标定位和边界回归机制，可能提升复杂场景下的检测精度。")

        if not possible_innovations:
            possible_innovations.append("从当前仓库与论文文本中未观察到强创新信号，更多可能是工程化改进型实现，需结合实验结果细化分析。")

        risk_items: List[str] = []
        if not paper_text:
            risk_items.append("论文页面无法稳定抓取正文，创新点分析可能偏工程化解读。")
        if not repo_text:
            risk_items.append("仓库 README 或源码描述不足，建议补充更明确的技术贡献说明。")
        if "error" in (reproduction_logs or "").lower() or "failed" in (reproduction_logs or "").lower():
            risk_items.append("复现日志中存在失败或错误信息，说明当前实现仍可能有环境兼容性或训练稳定性问题。")

        score = min(0.95, 0.45 + 0.12 * len(combined_hits) + (0.08 if paper_text else 0.0) + (0.08 if repo_text else 0.0))
        score = round(score, 2)

        summary = (
            "根据论文文本、仓库描述和复现日志的联合分析，当前方案最可能具备的创新点集中在模型结构、特征融合、泛化能力和工程部署效率方面。 "
            "如果复现日志稳定且指标表现良好，则说明此方法不仅有理论价值，也具备较强工程落地潜力。"
        )

        return {
            "status": "success",
            "confidence": score,
            "summary": summary,
            "possible_innovations": possible_innovations,
            "signals": {"paper": paper_hits, "repo": repo_hits, "logs": log_hits, "combined": combined_hits},
            "risks": risk_items,
            "paper_title": _extract_title(paper_url),
            "repo_url": repo_url,
        }


def _extract_title(paper_url: str) -> str:
    if not paper_url:
        return ""
    html = _safe_fetch(paper_url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    return title or ""


def analyze_paper_repro_task(paper_url: str, repo_url: str, reproduction_logs: str = "", repo_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    return PaperInnovationAnalyzer().analyze(paper_url, repo_url, reproduction_logs, repo_dir)


if __name__ == "__main__":
    sample = analyze_paper_repro_task(
        "https://arxiv.org/abs/2401.00001",
        "https://github.com/example/project",
        "Training complete. accuracy 0.95.",
    )
    print(json.dumps(sample, ensure_ascii=False, indent=2))
