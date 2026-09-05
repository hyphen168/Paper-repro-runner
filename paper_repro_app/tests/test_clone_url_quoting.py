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


def test_double_ghfast_prefix_unwrapped_once():
    """历史/粘贴可能已含加速前缀：ghfast 套 ghfast 必须还原为单层，杜绝 403。"""
    runner = _runner("https://ghfast.top/https://ghfast.top/https://github.com/DL4mHealth/Medformer/")
    cmd = next(s["command"] for s in runner.build_pipeline() if s["id"] == "clone")
    assert "https://ghfast.top/https://ghfast.top/" not in cmd
    assert "https://ghfast.top/https://github.com/DL4mHealth/Medformer/" in cmd
    # 官方源仍作为备用存在（输入带尾斜杠，故备用也带尾斜杠）
    assert '"https://github.com/DL4mHealth/Medformer/"' in cmd


def test_unwrap_ghfast_power():
    from paper_repro_app.remote_runner import _unwrap_ghfast
    base = "https://github.com/a/b"
    assert _unwrap_ghfast(f"https://ghfast.top/{base}") == base
    assert _unwrap_ghfast("https://ghfast.top/https://ghfast.top/https://github.com/a/b/") == base + "/"
    assert _unwrap_ghfast(base) == base
    assert _unwrap_ghfast("https://example.com/x") == "https://example.com/x"


def test_plain_github_uses_single_accel_with_official_alt():
    runner = _runner("https://github.com/tonmoy-hossain/Locus")
    cmd = next(s["command"] for s in runner.build_pipeline() if s["id"] == "clone")
    # @SRC@ 在模板中出现多处，至少一处为单层加速地址；且不带双前缀
    assert cmd.count("https://ghfast.top/https://github.com/tonmoy-hossain/Locus") >= 1
    assert "ghfast.top/https://ghfast.top/" not in cmd
