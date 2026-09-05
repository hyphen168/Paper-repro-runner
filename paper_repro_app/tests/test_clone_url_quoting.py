"""clone URL 引号回归：模板内 URL 已双引号包裹，禁止二次 shlex.quote（曾致 git
收到字面单引号 → protocol ''https' is not supported）。"""
from __future__ import annotations

from paper_repro_app.remote_runner import RemoteRunner, _clean_clone_url


def _runner(repo: str):
    return RemoteRunner({
        "host": "example.com", "user": "root",
        "repo_url": repo, "clone_url": repo,
        "remote_workdir": "/workspace/demo",
        "environment_mode": "venv",
    })


def test_clone_step_embeds_bare_url_in_double_quotes():
    runner = _runner("https://github.com/tonmoy-hossain/Locus")
    cmd = next(s["command"] for s in runner.build_pipeline() if s["id"] == "clone")
    assert "'https://github.com" not in cmd, "URL 被二次引用，git 会报 protocol ''https'"
    assert '"https://github.com/tonmoy-hossain/Locus"' in cmd


def test_clean_clone_url_strips_wrapped_quotes():
    assert _clean_clone_url("'https://github.com/a/b'") == "https://github.com/a/b"
    assert _clean_clone_url('"https://github.com/a/b"') == "https://github.com/a/b"
    assert _clean_clone_url("  https://github.com/a/b  ") == "https://github.com/a/b"
    assert _clean_clone_url(None) == ""


def test_clone_step_with_quoted_pasted_url_still_clean():
    runner = _runner("'https://github.com/tonmoy-hossain/Locus'")
    cmd = next(s["command"] for s in runner.build_pipeline() if s["id"] == "clone")
    assert "'https://github.com" not in cmd
    assert '"https://github.com/tonmoy-hossain/Locus"' in cmd
