from __future__ import annotations

import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
VENV_DIR = APP_DIR / ".venv"
PYTHON_EXE = APP_DIR / r".venv\Scripts\python.exe"
DEFAULT_PORT = 8505


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


PORT = find_free_port()
LOCAL_URL = f"http://127.0.0.1:{PORT}"


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


def ensure_virtualenv() -> None:
    if not VENV_DIR.exists():
        print("[Paper Repro] Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], cwd=str(APP_DIR), check=True)


def ensure_dependencies() -> None:
    if not PYTHON_EXE.exists():
        raise FileNotFoundError(f"Virtual environment Python not found: {PYTHON_EXE}")

    print("[Paper Repro] Installing dependencies...")
    result = subprocess.run(
        [str(PYTHON_EXE), "-m", "pip", "install", "-r", "requirements.txt", "--disable-pip-version-check"],
        cwd=str(APP_DIR),
        check=False,
    )
    if result.returncode != 0:
        print("[Paper Repro] Dependency install failed. Close any running Python/Streamlit process and try again.")
        raise SystemExit(result.returncode)


def open_browser() -> None:
    try:
        webbrowser.open(LOCAL_URL, new=2, autoraise=True)
        print(f"[Paper Repro] Opening browser: {LOCAL_URL}")
        for ip in get_local_ips():
            if ip != "127.0.0.1":
                print(f"[Paper Repro] Phone/LAN access URL: http://{ip}:{PORT}")
    except Exception as exc:
        print(f"[Paper Repro] Could not open browser automatically: {exc}")


def start_app() -> None:
    if is_port_in_use(PORT):
        print(f"[Paper Repro] App already running at {LOCAL_URL}")
        open_browser()
        return

    print(f"[Paper Repro] Starting app at {LOCAL_URL}")
    for ip in get_local_ips():
        if ip != "127.0.0.1":
            print(f"[Paper Repro] LAN/mobile access: http://{ip}:{PORT}")
    open_browser()

    subprocess.run(
        [
            str(PYTHON_EXE),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.headless",
            "true",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            str(PORT),
        ],
        cwd=str(APP_DIR),
        check=False,
    )


if __name__ == "__main__":
    ensure_virtualenv()
    ensure_dependencies()
    start_app()
