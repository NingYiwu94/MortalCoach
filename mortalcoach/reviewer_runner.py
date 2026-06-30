from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from link_utils import parse_main_input


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


DEFAULT_CONFIG = {
    "mjai_reviewer": "mjai-reviewer",
    "mortal_exe": "mortal",
    "mortal_cfg": "path/to/mortal/config.toml",
    "node": "node",
    "tensoul_dir": "./vendor/tensoul",
    "majsoul_base": "https://game.maj-soul.com",
    "majsoul_gateway": "",
    "access_token": "",
}


def load_config() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as f:
        user_cfg = json.load(f)
    cfg = DEFAULT_CONFIG.copy()
    cfg.update({k: str(v) for k, v in user_cfg.items()})
    return cfg


def review_tenhou_url(url: str, *, player_id: int | None = None) -> dict[str, Any]:
    cfg = load_config()
    cmd = [
        cfg["mjai_reviewer"],
        "-e",
        "mortal",
        "-u",
        url,
        "--json",
        "--no-open",
        "--mortal-exe",
        cfg["mortal_exe"],
        "--mortal-cfg",
        cfg["mortal_cfg"],
        "-o",
        "-",
    ]
    if player_id is not None:
        cmd.extend(["-a", str(player_id)])

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"mjai-reviewer failed with code {proc.returncode}")
    return json.loads(proc.stdout)


def review_link(url: str, *, player_id: int | None = None) -> dict[str, Any]:
    if "tenhou.net" in url:
        return review_tenhou_url(url, player_id=player_id)
    if "maj-soul.com" in url or "mahjongsoul" in url:
        return review_majsoul_url(url, player_id=player_id)
    raise RuntimeError(
        "Unsupported log URL. Currently supported: Tenhou URL and Mahjong Soul URL."
    )


def review_tenhou_json_file(path: str, *, player_id: int) -> dict[str, Any]:
    cfg = load_config()
    cmd = [
        cfg["mjai_reviewer"],
        "-e",
        "mortal",
        "-i",
        path,
        "-a",
        str(player_id),
        "--json",
        "--no-open",
        "--mortal-exe",
        cfg["mortal_exe"],
        "--mortal-cfg",
        cfg["mortal_cfg"],
        "-o",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"mjai-reviewer failed with code {proc.returncode}")
    return json.loads(proc.stdout)


def review_majsoul_url(url: str, *, player_id: int | None = None) -> dict[str, Any]:
    parsed = parse_main_input(url)
    if parsed.kind != "majsoul_url":
        raise RuntimeError("Not a Mahjong Soul URL.")
    tenhou_log = convert_majsoul_to_tenhou(parsed.value)
    actor = player_id
    if actor is None:
        actor = tenhou_log.get("_target_actor")
    if actor is None:
        raise RuntimeError(
            "无法自动识别复盘玩家。请在雀魂链接中保留 _a... 后缀，或手动选择玩家 ID。"
        )
    actor = int(actor)
    tenhou_log.pop("_target_actor", None)

    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
        json.dump(tenhou_log, f, ensure_ascii=False)
        tmp_path = f.name
    try:
        return review_tenhou_json_file(tmp_path, player_id=actor)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def convert_majsoul_to_tenhou(url: str) -> dict[str, Any]:
    cfg = load_config()
    tensoul_dir = (ROOT / cfg["tensoul_dir"]).resolve()
    if not tensoul_dir.exists():
        raise RuntimeError(
            "未找到本地 tensoul 转换器。请先运行 scripts/setup_tensoul.ps1，"
            "或在 config.json 中设置 tensoul_dir。"
        )
    if not cfg.get("access_token"):
        raise RuntimeError(
            "尚未完成雀魂授权。请在软件左侧点击“启动雀魂授权向导”，"
            "在打开的雀魂窗口中登录后再重新分析。"
        )

    record_id = extract_majsoul_record_id(url)
    env = os.environ.copy()
    env["ACCESS_TOKEN"] = cfg["access_token"]
    env["MJS_BASE"] = cfg.get("majsoul_base") or "https://game.maj-soul.com"
    gateway = cfg.get("majsoul_gateway") or ""
    if gateway:
        env["MJS_GATEWAY"] = gateway

    proc = subprocess.run(
        [cfg.get("node") or "node", ".", record_id],
        cwd=tensoul_dir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"tensoul failed with code {proc.returncode}")
    return json.loads(proc.stdout)


def extract_majsoul_record_id(url: str) -> str:
    parsed = parse_main_input(url)
    if parsed.kind != "majsoul_url":
        raise RuntimeError("Not a Mahjong Soul URL.")
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(parsed.value).query)
    paipu = qs.get("paipu", [""])[0]
    if not paipu:
        raise RuntimeError("雀魂链接中没有 paipu 参数。")
    return paipu
