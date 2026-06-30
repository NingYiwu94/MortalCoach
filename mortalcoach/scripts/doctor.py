from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warn(message: str) -> None:
    print(f"[WARN] {message}")


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def check_python() -> bool:
    version = sys.version_info
    if version >= (3, 10):
        ok(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    fail("Python 3.10+ is recommended")
    return False


def check_files() -> bool:
    required = [
        "app.py",
        "db.py",
        "desktop/main.js",
        "static/index.html",
        "../killer_mortal_gui/index.html",
    ]
    missing = [item for item in required if not (ROOT / item).resolve().exists()]
    if missing:
        fail(f"Missing files: {', '.join(missing)}")
        return False
    ok("Project files")
    return True


def check_database() -> bool:
    db_path = ROOT / "data" / "mortalcoach.sqlite3"
    if not db_path.exists():
        warn("Database does not exist yet; it will be created on first run")
        return True
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("pragma integrity_check").fetchone()
        ok(f"SQLite database: {db_path}")
        return True
    except Exception as exc:
        fail(f"SQLite check failed: {exc}")
        return False


def check_node() -> bool:
    node = shutil.which("node")
    npm = shutil.which("npm")
    common_node = Path(r"C:\Program Files\nodejs\node.exe")
    common_npm = Path(r"C:\Program Files\nodejs\npm.cmd")
    if (not node or not npm) and common_node.exists() and common_npm.exists():
        node = str(common_node)
        npm = str(common_npm)
    if node and npm:
        ok(f"Node: {node}")
        ok(f"npm: {npm}")
        return True
    warn("Node/npm not found. Electron desktop launch needs Node.js; browser mode can still use python app.py.")
    return True


def check_electron_env() -> bool:
    if os.environ.get("ELECTRON_RUN_AS_NODE"):
        warn("ELECTRON_RUN_AS_NODE is set in the environment. Start-MortalCoach.bat clears it before launching Electron.")
    return True


def check_electron() -> bool:
    electron = ROOT / "node_modules" / "electron" / "dist" / "electron.exe"
    if electron.exists():
        ok("Electron installed")
        return True
    warn("Electron is not installed. Start-MortalCoach.bat will try npm install on first run.")
    return True


def main() -> int:
    checks = [
        check_python(),
        check_files(),
        check_database(),
        check_node(),
        check_electron_env(),
        check_electron(),
    ]
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
