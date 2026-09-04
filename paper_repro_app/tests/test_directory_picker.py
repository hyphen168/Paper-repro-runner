"""本地输出目录选择器回归：PowerShell 原生选择成功路径与全失败回退。

注意：测试环境禁止弹真实 GUI（Tk askdirectory 会阻塞挂起）；用 autouse fixture
关闭，并对 tkinter 回落分支用桩覆盖。所有桩均用 monkeypatch，保证同进程其它
测试文件不受污染。
"""
from __future__ import annotations

import os

import pytest

import app as app_mod


@pytest.fixture(autouse=True)
def _no_gui_dialog(monkeypatch):
    """所有用例都禁用真实 Tk 对话框，避免 CI/本机被 GUI 阻塞。"""
    monkeypatch.setattr(app_mod, "Tk", None)
    monkeypatch.setattr(app_mod, "askdirectory", None)


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
    default = str(tmp_path)
    got = app_mod.open_directory_dialog(default)
    assert got == os.path.abspath(default)


def test_picker_tk_fallback_used_when_tk_available(tmp_path, monkeypatch):
    """PowerShell 不可用时应走 Tk 回落分支（桩覆盖，不弹真实窗口）。"""
    target = tmp_path / "tk-out"

    def _boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(app_mod.subprocess, "run", _boom)

    class _FakeTk:
        def withdraw(self):
            return None

        def attributes(self, *a, **k):
            return None

        def destroy(self):
            return None

    monkeypatch.setattr(app_mod, "Tk", lambda: _FakeTk())
    monkeypatch.setattr(app_mod, "askdirectory", lambda initialdir, title: str(target))
    got = app_mod.open_directory_dialog(str(tmp_path))
    assert os.path.abspath(got) == os.path.abspath(str(target))
