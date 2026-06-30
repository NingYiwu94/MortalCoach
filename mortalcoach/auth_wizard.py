from __future__ import annotations

import json
import time
from pathlib import Path

from reviewer_runner import CONFIG_PATH, DEFAULT_CONFIG, load_config


ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / "data" / "majsoul_browser_profile"


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Run: python -m pip install playwright && python -m playwright install chromium"
        ) from exc

    cfg = load_config()
    base_url = cfg.get("majsoul_base") or "https://game.maj-soul.com"
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 820},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        print("Please login to Mahjong Soul in the opened browser window.", flush=True)

        token = wait_for_access_token(context, timeout_seconds=300)
        write_access_token(token)
        print("Mahjong Soul authorization saved.", flush=True)
        context.close()


def wait_for_access_token(context, timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for page in list(context.pages):
            try:
                token = page.evaluate(
                    "() => globalThis.GameMgr && GameMgr.Inst && GameMgr.Inst.access_token || ''"
                )
            except Exception:
                token = ""
            if isinstance(token, str) and token.strip():
                return token.strip()
        time.sleep(1)
    raise TimeoutError("Timed out waiting for Mahjong Soul login.")


def write_access_token(token: str) -> None:
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8-sig") as f:
            cfg.update(json.load(f))
    cfg["access_token"] = token
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
