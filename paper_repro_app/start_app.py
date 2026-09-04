"""一键启动引导：负责把"拷贝过来的代码文件夹"变成"可运行的应用"。

启动流程（全部自动）：
1. 校验本机 Python 版本（>= 3.11，附安装指引）
2. 校验虚拟环境健康（拷贝过来的坏 .venv 自动重建）
3. 依赖指纹比对（requirements.txt 没变就跳过安装，秒开）
4. 安装依赖（PyPI 失败自动切换清华/阿里镜像重试）
5. 启动 Streamlit 并打开浏览器

设计目标：朋友拿到 zip 解压后双击 start_app.bat 即可使用。
"""
from __future__ import annotations

import hashlib
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
VENV_DIR = APP_DIR / ".venv"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe"
REQUIREMENTS_FILE = APP_DIR / "requirements.txt"
FINGERPRINT_FILE = VENV_DIR / ".requirements.sha256"
DEFAULT_PORT = 8505
MIN_PYTHON = (3, 11)

# 国内镜像候选（自动测速择优，无需用户配置）
PIP_INDEX_FALLBACKS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://pypi.doubanio.com/simple",
    "https://mirrors.ustc.edu.cn/pypi/simple",
    "https://repo.huaweicloud.com/repository/pypi/simple",
]

PYPI_OFFICIAL = "https://pypi.org/simple"

PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"


def _log(message: str) -> None:
    print(f"[Paper Repro] {message}", flush=True)


def find_free_port(start_port: int = DEFAULT_PORT, max_tries: int = 20) -> int:
    for port in range(start_port, start_port + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    return start_port


def get_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(
            socket.gethostname(), None, type=socket.SOCK_DGRAM
        ):
            ip = sockaddr[0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    if not ips:
        ips = ["127.0.0.1"]
    return ips


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


# ---------------------------------------------------------------------------
# 引导逻辑
# ---------------------------------------------------------------------------

def check_system_python() -> None:
    """检查当前解释器版本；过低时给出明确的安装指引。"""
    if sys.version_info < MIN_PYTHON:
        _log("=" * 60)
        _log(f"检测到 Python {sys.version_info.major}.{sys.version_info.minor}，")
        _log("本应用需要 Python 3.11 或更高版本（建议 3.12）。")
        _log("请到官网下载安装（安装时勾选 Add python.exe to PATH）：")
        _log(f"  {PYTHON_DOWNLOAD_URL}")
        _log("安装完成后重新双击 start_app.bat 即可。")
        _log("=" * 60)
        try:
            webbrowser.open(PYTHON_DOWNLOAD_URL)
        except Exception:
            pass
        raise SystemExit(1)


def venv_is_healthy() -> bool:
    """校验虚拟环境是否可用。

    venv 记录创建机器的 Python 绝对路径（pyvenv.cfg 的 home 字段），
    整个文件夹拷贝到别的电脑后该路径通常失效，必须重建。
    """
    if not PYTHON_EXE.exists():
        return False

    cfg_file = VENV_DIR / "pyvenv.cfg"
    if cfg_file.exists():
        home = ""
        for line in cfg_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().lower().startswith("home"):
                home = line.split("=", 1)[-1].strip()
                break
        if home and not (Path(home) / "python.exe").exists():
            return False

    try:
        result = subprocess.run(
            [str(PYTHON_EXE), "-c", "import sys, venv"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_virtualenv() -> None:
    if not venv_is_healthy():
        if VENV_DIR.exists():
            _log("检测到损坏的虚拟环境（可能来自其他电脑），自动重建...")
            shutil.rmtree(VENV_DIR, ignore_errors=True)
        _log("正在创建虚拟环境（仅首次需要，约 10 秒）...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            cwd=str(APP_DIR),
            check=True,
        )


def requirements_fingerprint() -> str:
    if not REQUIREMENTS_FILE.exists():
        return "no-requirements"
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def dependencies_current() -> bool:
    """requirements.txt 与上次安装时一致则跳过安装。"""
    if not FINGERPRINT_FILE.exists():
        return False
    try:
        return FINGERPRINT_FILE.read_text(encoding="utf-8").strip() == requirements_fingerprint()
    except OSError:
        return False


def run_pip_install(index_url: str | None) -> int:
    command = [
        str(PYTHON_EXE),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(REQUIREMENTS_FILE),
    ]
    if index_url:
        command += ["-i", index_url]
    result = subprocess.run(command, cwd=str(APP_DIR), check=False)
    return result.returncode


def _probe_index(url: str, timeout: float = 4.0) -> float | None:
    """探测镜像源连通性，返回响应耗时（秒）；不可用返回 None。"""
    import urllib.request

    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "paper-repro-boot/1.0"})
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status < 400:
                return time.monotonic() - start
    except Exception:
        pass
    # 部分源不支持 HEAD，退化为 GET 首字节
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "paper-repro-boot/1.0"})
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(1)
            if resp.status < 400:
                return time.monotonic() - start
    except Exception:
        pass
    return None


def pick_best_index() -> str | None:
    """并发探测候选镜像，返回响应最快的可用源（含官方 PyPI）；全部不可用返回 None。"""
    import concurrent.futures

    candidates = [PYPI_OFFICIAL] + PIP_INDEX_FALLBACKS
    results: dict[str, float | None] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
        futures = {pool.submit(_probe_index, url): url for url in candidates}
        for fut in concurrent.futures.as_completed(futures, timeout=12):
            url = futures[fut]
            try:
                results[url] = fut.result()
            except Exception:
                results[url] = None
    alive = [(t, url) for url, t in results.items() if t is not None]
    if not alive:
        return None
    alive.sort()
    return alive[0][1]


def ensure_dependencies() -> None:
    if not PYTHON_EXE.exists():
        raise FileNotFoundError(f"虚拟环境 Python 不存在: {PYTHON_EXE}")

    if dependencies_current():
        _log("依赖已就绪，跳过安装（秒开）。")
        return

    _log("正在安装依赖（仅首次或依赖变化时，约 1-3 分钟）...")

    # 自动测速择优：并发探测官方源与全部国内镜像，选响应最快的可用源
    best = pick_best_index()
    if best:
        _log(f"镜像测速完成，自动选用最快可用源: {best}")
        if run_pip_install(best) == 0:
            FINGERPRINT_FILE.write_text(requirements_fingerprint(), encoding="utf-8")
            _log("依赖安装完成。")
            return
        _log("首选源安装失败，尝试其余镜像...")
    else:
        _log("网络探测失败（可能离线），按顺序逐个尝试官方源与镜像...")

    # 保底：按固定顺序逐个重试（含官方源兜底）
    ordered = [PYPI_OFFICIAL] + PIP_INDEX_FALLBACKS
    for mirror in ordered:
        if mirror == best:
            continue  # 已试过
        _log(f"正在尝试: {mirror}")
        if run_pip_install(mirror) == 0:
            FINGERPRINT_FILE.write_text(requirements_fingerprint(), encoding="utf-8")
            _log("依赖安装完成。")
            return

    _log("依赖安装失败。请检查网络后重新双击 start_app.bat。")
    _log("若持续失败，可手动执行: .venv\\Scripts\\python -m pip install -r requirements.txt")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 应用启动
# ---------------------------------------------------------------------------

def open_browser(url: str, port: int) -> None:
    try:
        webbrowser.open(url, new=2, autoraise=True)
        _log(f"已打开浏览器: {url}")
    except Exception as exc:  # pragma: no cover
        _log(f"未能自动打开浏览器（不影响使用，手动访问 {url}）: {exc}")


def start_app(expose: str = "", no_browser: bool = False) -> None:
    # 若默认端口已被占用，大概率是应用已在运行，直接打开浏览器而非再起一个实例
    if is_port_in_use(DEFAULT_PORT):
        url = f"http://127.0.0.1:{DEFAULT_PORT}"
        _log(f"应用已在运行: {url}")
        open_browser(url, DEFAULT_PORT)
        return

    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    bind_address = "127.0.0.1"
    env_extra = {}
    if expose in ("lan", "tunnel"):
        env_extra["PAPER_REPRO_EXPOSE"] = expose
        if expose == "lan":
            bind_address = "0.0.0.0"
            _log("局域网访问模式：将向同网段设备开放（已启用访问口令门）。")

    _log(f"应用启动中: {url}")
    # 先起服务并等待端口就绪（≤20s）再打开浏览器，避免"无法访问此网站"
    import os
    full_env = dict(os.environ)
    full_env.update(env_extra)
    proc = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.headless",
            "true",
            "--server.address",
            bind_address,
            "--server.port",
            str(port),
        ],
        cwd=str(APP_DIR),
        env=full_env,
    )
    deadline = time.time() + 20
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        if is_port_in_use(port):
            ready = True
            break
        time.sleep(0.4)
    if ready:
        if no_browser:
            _log(f"服务已就绪（不打开浏览器）: {url}")
        else:
            _log("服务已就绪，打开浏览器...")
            open_browser(url, port)
        if expose == "lan":
            for ip in get_local_ips():
                if ip != "127.0.0.1":
                    _log(f"手机/平板访问（同 WiFi）: http://{ip}:{port}")
                    _log("提示：首次访问需输入访问口令（在页面设置）；如无法连接请以管理员运行 open_firewall.bat 放行防火墙。")
    else:
        _log("服务启动失败或超时（20s 内未就绪）。")
    rc = proc.wait()
    if rc != 0:
        _log(f"应用进程异常退出（退出码 {rc}）。")
        _log("排查：1) 查看上方日志定位具体错误；2) 可手动运行 .venv\\Scripts\\python -m streamlit run app.py 查看完整报错；3) 或删除 .venv 文件夹后重新双击 start_app.bat 重建环境。")
        raise SystemExit(rc)


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="论文复现助手启动器")
    _parser.add_argument("--expose", choices=["lan", "tunnel"], default="",
                         help="远程访问模式：lan=局域网(0.0.0.0+口令)；tunnel=供 SSH 反隧回环（仍绑 127.0.0.1）")
    _parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器（供开机自启常驻）")
    _args = _parser.parse_args()
    check_system_python()
    ensure_virtualenv()
    ensure_dependencies()
    start_app(expose=_args.expose, no_browser=_args.no_browser)
