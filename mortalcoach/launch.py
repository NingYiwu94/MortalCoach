from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("MORTALCOACH_PORT", "8766"))
URL = f"http://{HOST}:{PORT}"


def main() -> None:
    proc = None
    if not is_port_open(HOST, PORT):
        env = os.environ.copy()
        env["MORTALCOACH_PORT"] = str(PORT)
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_until_ready(URL)

    open_app_window(URL)

    if proc is not None:
        print("MortalCoach is running.")
        print("Close this window to stop the local service.")
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def wait_until_ready(url: str) -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/games", timeout=0.5).read()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("MortalCoach did not start in time.")


def open_app_window(url: str) -> None:
    browsers = [
        os.environ.get("ProgramFiles(x86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("ProgramFiles", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("ProgramFiles", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("ProgramFiles(x86)", "") + r"\Google\Chrome\Application\chrome.exe",
    ]
    for browser in browsers:
        if browser and Path(browser).exists():
            subprocess.Popen([browser, f"--app={url}"])
            return
    webbrowser.open(url)


if __name__ == "__main__":
    main()
