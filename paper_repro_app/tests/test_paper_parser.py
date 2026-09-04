"""论文→仓库解析回归：必须忽略 HF 文档页/个人主页，只接受真仓库形态。"""
from __future__ import annotations

import paper_repro_app.paper_parser as pp


def test_looks_like_repo_url_accepts_real_repos():
    ok = [
        "https://github.com/tonmoy-hossain/Locus",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b/blob/main/train.py",
        "https://gitlab.com/group/proj",
        "https://gitee.com/hyphen168/Yolov5m-NEU-DET",
        "https://huggingface.co/tonmoy-hossain/Locus",
        "https://huggingface.co/google/vit-base-patch16-224",
    ]
    for u in ok:
        assert pp.looks_like_repo_url(u), u


def test_looks_like_repo_url_rejects_docs_and_homepages():
    bad = [
        "https://huggingface.co/docs/hub/spaces/",        # 上次踩坑：HF 文档页
        "https://huggingface.co/docs",
        "https://huggingface.co/blog/peft",
        "https://huggingface.co/models",
        "https://github.com/tonmoy-hossain",               # 个人主页（仅 1 段）
        "https://github.com",                              # 平台首页
        "https://github.com/orgs/org/repositories",
        "https://gitlab.com/explore",
        "http://example.com/a/b",
        "",
        "C:/Users/me/repo",                                # 本地文件地址不算仓库链接
    ]
    for u in bad:
        assert not pp.looks_like_repo_url(u), u


def test_extract_repo_url_skips_hf_docs_and_returns_github(monkeypatch):
    """页面里先出现 HF 文档页链接，后出现真 GitHub 仓库链接 → 必须返回 GitHub 仓库。"""

    class _Resp:
        text = (
            "<html><body>"
            "<a href='https://huggingface.co/docs/hub/spaces/'>Spaces docs</a>"
            "<a href='https://github.com/tonmoy-hossain/Locus'>Code</a>"
            "<a href='https://huggingface.co/blog/peft'>blog</a>"
            "</body></html>"
        )

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pp.requests, "get", lambda url, timeout=None: _Resp())
    assert pp.extract_repo_url("https://arxiv.org/abs/2607.10851") == "https://github.com/tonmoy-hossain/Locus"


def test_extract_repo_url_prefers_hf_model_over_hf_docs(monkeypatch):
    """只有 HF 链接时：模型仓库链接被采纳，文档链接被忽略。"""

    class _Resp:
        text = (
            "<a href='https://huggingface.co/docs/hub/spaces'>docs</a>"
            "<a href='https://huggingface.co/tonmoy-hossain/Locus'>repo</a>"
        )

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pp.requests, "get", lambda url, timeout=None: _Resp())
    assert pp.extract_repo_url("https://doi.org/10.48550/arXiv.2607.10851") == "https://huggingface.co/tonmoy-hossain/Locus"


def test_extract_repo_url_no_repo_returns_none(monkeypatch):
    class _Resp:
        text = "<a href='https://huggingface.co/docs/hub'>none</a><p>no repo</p>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pp.requests, "get", lambda url, timeout=None: _Resp())
    assert pp.extract_repo_url("https://example.org/paper") is None


def test_extract_repo_url_non_http_input_safe():
    assert pp.extract_repo_url("C:/Users/me/paper.html") is None
    assert pp.extract_repo_url("") is None
    assert pp.extract_paper_metadata("C:/nope")["repo_url"] == ""
