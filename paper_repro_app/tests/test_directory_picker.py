"""本地输出目录选择器回归：PowerShell 原生选择成功路径与全失败回退。"""
from __future__ import annotations

import os

import app as app_mod


def test_picker_powershell_returns_selected(tmp_path, monkeypatch):
    target = tmp_path / "my-output"
    target.mkdir()

    class _Proc:
        stdout = str(target).encode("utf-8")

    monkeypatch.setattr(app_mod.subprocess, "run", lambda *a, **k: _Proc())
    got = app_mod.open_directory_dialog(str(tmp_path))
    assert os.path.abspath(got) == os.path.abspath(str(target))


def test_picker_powershell_cancel_falls_to_default(tmp_path, monkeypatch):
    class _Empty:
        stdout = b""

    monkeypatch.setattr(app_mod.subprocess, "run", lambda *a, **k: _Empty())
    default = str(tmp_path / "fallback")
    got = app_mod.open_directory_dialog(default)
    assert got == os.path.abspath(default)


def test_picker_all_mechanisms_unavailable_returns_default(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(app_mod.subprocess, "run", _boom)
    monkeypatch.setattr(app_mod, "Tk", None)
    monkeypatch.setattr(app_mod, "askdirectory", None)
    default = str(tmp_path)
    got = app_mod.open_directory_dialog(default)
    assert got == os.path.abspath(default)
