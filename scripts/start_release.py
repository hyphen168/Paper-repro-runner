from __future__ import annotations

import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "paper_repro_app"
VENV_DIR = ROOT / ".venv"
PORT = 8505
LOCAL_URL = f"http://127.0.0.1:{PORT}"


def get_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(
            socket.gethostname(), None, type=socket.SOCK_DGRAM
        ):
            ip = sockaddr[0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def ensure_virtualenv() -> Path:
    if not VENV_DIR.exists():
        print("[Release] Creating project virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], cwd=str(ROOT), check=True)
    venv_python = VENV_DIR / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    if not venv_python.exists():
        raise FileNotFoundError(f"Virtual environment Python not found: {venv_python}")
    return venv_python


def install_dependencies(python_exe: Path) -> None:
    print("[Release] Installing project dependencies...")
    for requirement_file in [ROOT / "requirements.txt", APP_DIR / "requirements.txt"]:
        if requirement_file.exists():
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "install", "-r", str(requirement_file), "--disable-pip-version-check"],
                cwd=str(ROOT),
                check=False,
            )
            if result.returncode != 0:
                raise SystemExit(f"Dependency installation failed for {requirement_file}: exit code {result.returncode}")


def open_browser() -> None:
    try:
        webbrowser.open(LOCAL_URL, new=2, autoraise=True)
        print(f"[Release] Browser opened: {LOCAL_URL}")
        for ip in get_local_ips():
            if ip != "127.0.0.1":
                print(f"[Release] LAN access URL: http://{ip}:{PORT}")
    except Exception as exc:  # pragma: no cover - browser can fail in headless environments
        print(f"[Release] Could not open the browser automatically: {exc}")


def start_streamlit(python_exe: Path) -> None:
    if is_port_in_use(PORT):
        print(f"[Release] App already running at {LOCAL_URL}")
        open_browser()
        return

    print(f"[Release] Starting app at {LOCAL_URL}")
    for ip in get_local_ips():
        if ip != "127.0.0.1":
            print(f"[Release] LAN/mobile access: http://{ip}:{PORT}")
    open_browser()

    subprocess.run(
        [
            str(python_exe),
            "-m",
            "streamlit",
            "run",
            "paper_repro_app/app.py",
            "--server.headless",
            "true",
            "--server.address",
            "0.0.0.0",
            "--server.port",
            str(PORT),
        ],
        cwd=str(ROOT),
        check=False,
    )


def main() -> None:
    python_exe = ensure_virtualenv()
    install_dependencies(python_exe)
    start_streamlit(python_exe)


if __name__ == "__main__":
    main()
