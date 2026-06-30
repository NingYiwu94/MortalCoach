from __future__ import annotations

import json
import math
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

import db
from analysis import action_to_text
from link_utils import parse_main_input
from official_runner import run_official_review
from reviewer_runner import load_config, review_link


ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
STATIC = RESOURCE_ROOT / "static"
KILLER_GUI = RESOURCE_ROOT / "killer_mortal_gui"
if not KILLER_GUI.exists():
    KILLER_GUI = ROOT.parent / "killer_mortal_gui"
AUTH_JOB = {
    "running": False,
    "ok": False,
    "message": "",
}
AUTH_LOCK = threading.Lock()
OFFICIAL_JOB = {
    "running": False,
    "ok": False,
    "message": "",
    "game_id": None,
}
OFFICIAL_LOCK = threading.Lock()


class AppHandler(BaseHTTPRequestHandler):
    server_version = "MortalCoach/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.send_file(STATIC / "index.html")
        elif path == "/killer" or path == "/killer/":
            self.send_file(KILLER_GUI / "index.html")
        elif path == "/api/games":
            self.send_json(db.list_games())
        elif path == "/api/stats":
            self.send_json(db.get_stats())
        elif path == "/api/export":
            self.send_json(db.export_data())
        elif path == "/api/profile":
            self.send_json(db.get_profile())
        elif path == "/api/coach/brief":
            self.send_json(build_coach_brief())
        elif path == "/api/auth/status":
            self.send_json(auth_status())
        elif path == "/api/official/status":
            self.send_json(official_status())
        elif path == "/api/marks":
            self.send_json(db.list_marked_errors())
        elif path.startswith("/api/games/"):
            self.handle_game_get(path, parsed.query)
        elif path.startswith("/killer/"):
            self.handle_killer_asset(path)
        else:
            target = (STATIC / path.lstrip("/")).resolve()
            if str(target).startswith(str(STATIC.resolve())) and target.exists():
                self.send_file(target)
            else:
                self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/import-json":
                self.handle_import_json()
            elif parsed.path == "/api/import-input":
                self.handle_import_input()
            elif parsed.path == "/api/import-official":
                self.handle_import_official()
            elif parsed.path == "/api/review-url":
                self.handle_review_url()
            elif parsed.path == "/api/auth/majsoul/start":
                self.handle_auth_start()
            elif parsed.path == "/api/official/start":
                self.handle_official_start()
            elif parsed.path == "/api/official/find":
                self.handle_official_find()
            elif parsed.path == "/api/backup":
                self.send_json(db.create_backup())
            elif parsed.path.startswith("/api/errors/") and parsed.path.endswith("/mark"):
                self.handle_error_mark(parsed.path)
            elif parsed.path.startswith("/api/errors/") and parsed.path.endswith("/learning"):
                self.handle_error_learning(parsed.path)
            elif parsed.path.startswith("/api/games/") and parsed.path.endswith("/title"):
                self.handle_game_title_update(parsed.path)
            elif parsed.path == "/api/profile":
                self.send_json(db.save_profile(self.read_json()))
            elif parsed.path == "/api/profile/majsoul-sync":
                self.handle_majsoul_sync()
            else:
                self.send_error(404, "Not found")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/games/"):
            game_id = int(path.rstrip("/").split("/")[-1])
            ok = db.delete_game(game_id)
            self.send_json({"ok": ok}, status=200 if ok else 404)
        else:
            self.send_error(404, "Not found")

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/games/"):
                parts = path.rstrip("/").split("/")
                if len(parts) != 4:
                    self.send_error(404, "Not found")
                    return
                game_id = int(parts[-1])
                body = self.read_json()
                game = db.update_game_title(game_id, body.get("title") or "")
                if game is None:
                    self.send_error(404, "Game not found")
                    return
                self.send_json(game)
                return
            self.send_error(404, "Not found")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def handle_game_title_update(self, path: str) -> None:
        parts = path.rstrip("/").split("/")
        if len(parts) != 5 or parts[0] != "" or parts[1] != "api" or parts[2] != "games" or parts[4] != "title":
            self.send_error(404, "Not found")
            return
        game_id = int(parts[3])
        body = self.read_json()
        game = db.update_game_title(game_id, body.get("title") or "")
        if game is None:
            self.send_error(404, "Game not found")
            return
        self.send_json(game)

    def handle_majsoul_sync(self) -> None:
        payload = self.read_json()
        nickname = str(payload.get("majsoul_id") or db.get_profile().get("majsoul_id") or "").strip()
        if not nickname:
            self.send_json({"error": "请先填写雀魂昵称"}, status=400)
            return
        self.send_json(sync_majsoul_public_stats(nickname))

    def handle_game_get(self, path: str, query: str) -> None:
        parts = path.rstrip("/").split("/")
        if len(parts) < 4:
            self.send_error(404, "Not found")
            return
        game_id = int(parts[3])
        if len(parts) == 4:
            game = db.get_game(game_id)
            if game is None:
                self.send_error(404, "Game not found")
                return
            self.send_json(game)
            return
        if len(parts) == 5 and parts[4] == "errors":
            qs = parse_qs(query)
            limit = int(qs.get("limit", ["10"])[0])
            order = qs.get("order", ["chronological"])[0]
            errors = db.get_errors(game_id, limit=limit, order=order)
            for err in errors:
                err["expected_text"] = action_to_text(err.get("expected"))
                err["actual_text"] = action_to_text(err.get("actual"))
            self.send_json(errors)
            return
        if len(parts) == 5 and parts[4] == "review-data":
            qs = parse_qs(query)
            limit = int(qs.get("limit", ["10"])[0])
            order = qs.get("order", ["chronological"])[0]
            data = db.get_review_data(game_id, limit=limit, order=order)
            if data is None:
                self.send_error(404, "Game not found")
                return
            self.send_json(data)
            return
        if len(parts) == 5 and parts[4] == "killer-data":
            data = db.get_killer_data(game_id)
            if data is None:
                self.send_error(404, "KillerDucky JSON not found for this game")
                return
            self.send_json(data)
            return
        if len(parts) == 5 and parts[4] == "saved-html":
            game = db.get_game(game_id)
            if game is None:
                self.send_error(404, "Game not found")
                return
            raw = game.get("raw_json") or {}
            html = raw.get("raw_text") if isinstance(raw, dict) else ""
            if not html:
                html = "<!doctype html><meta charset='utf-8'><p>No saved HTML for this record.</p>"
            self.send_html(html)
            return
        self.send_error(404, "Not found")

    def handle_killer_asset(self, path: str) -> None:
        rel = path[len("/killer/"):] or "index.html"
        target = (KILLER_GUI / rel).resolve()
        if str(target).startswith(str(KILLER_GUI.resolve())) and target.exists():
            self.send_file(target)
            return
        self.send_error(404, "Not found")

    def handle_import_json(self) -> None:
        body = self.read_json()
        payload = body.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object or JSON string")
        title = body.get("title") or "Untitled review"
        game_id = db.add_game(
            payload,
            title=title,
            source=body.get("source") or "",
            platform=body.get("platform") or "",
            player=body.get("player") or "",
            tags=body.get("tags") or "",
            notes=body.get("notes") or "",
        )
        self.send_json({"id": game_id})

    def handle_import_input(self) -> None:
        body = self.read_json()
        raw = body.get("input") or body.get("payload") or ""
        parsed = parse_main_input(raw)
        title = body.get("title") or "Untitled review"
        tags = body.get("tags") or ""
        notes = body.get("notes") or ""
        rating_percent = body.get("rating_percent")

        if parsed.kind == "json":
            payload = json.loads(parsed.value)
            game_id = db.add_game(
                payload,
                title=title,
                source=body.get("source") or "",
                platform=body.get("platform") or "",
                player=body.get("player") or "",
                tags=tags,
                notes=notes,
            )
            self.send_json({"kind": "game", "id": game_id})
            return

        if parsed.kind in {"official_result_url", "official_result_html"}:
            source = parsed.value if parsed.kind == "official_result_url" else body.get("source") or "official result html"
            game_id = db.add_manual_game(
                title=title,
                source=source,
                platform="official",
                tags=tags,
                notes=notes,
                rating_percent=float(rating_percent) if rating_percent not in {None, ""} else None,
                raw_text=parsed.value if parsed.kind == "official_result_html" else "",
            )
            self.send_json({"kind": "bookmark", "id": game_id})
            return

        if parsed.kind == "tenhou_url":
            raise ValueError("这是天凤牌谱链接。当前主流程改为官方 Mortal 结果管理：请先在官方网页分析，再粘贴 mjai-reviewer JSON 或官方结果页链接保存。")

        if parsed.kind == "majsoul_url":
            raise ValueError("这是雀魂牌谱链接。当前主流程改为官方 Mortal 结果管理：请先把它粘贴到官方 Mortal 网页完成分析，再把结果 JSON 或结果页链接保存到 MortalCoach。")

        raise ValueError(f"unsupported input kind: {parsed.kind}")

    def handle_review_url(self) -> None:
        body = self.read_json()
        url = body.get("url")
        if not url:
            raise ValueError("url is required")
        player_id = body.get("player_id")
        parsed = parse_main_input(url)
        payload = review_link(url, player_id=player_id)
        title = body.get("title") or url
        game_id = db.add_game(
            payload,
            title=title,
            source=url,
            platform=parsed.platform,
            player=str(player_id) if player_id is not None else "",
            tags=body.get("tags") or "",
            notes=body.get("notes") or "",
        )
        self.send_json({"id": game_id})

    def handle_import_official(self) -> None:
        body = self.read_json()
        title = body.get("title") or "Official Mortal review"
        source = body.get("source") or ""
        original_url = body.get("original_url") or source
        result_url = body.get("result_url") or source
        html = body.get("html") or ""
        killer_json = body.get("killer_json") if isinstance(body.get("killer_json"), dict) else None
        rating_percent = body.get("rating_percent")
        errors = body.get("errors") if isinstance(body.get("errors"), list) else []
        requested_ui_mode = body.get("ui_mode") or "killerducky"
        actual_ui_mode = infer_official_result_mode(html, result_url or source, killer_json) or requested_ui_mode
        if actual_ui_mode == "classic" and requested_ui_mode == "killerducky" and looks_like_killer_url(result_url or source):
            actual_ui_mode = "killerducky"
        if requested_ui_mode == "killerducky" and actual_ui_mode == "classic":
            ui_mode = "classic"
        ui_mode = actual_ui_mode
        if ui_mode == "killerducky" and killer_json is None:
            try:
                killer_json = fetch_killer_json(result_url or source)
            except Exception:
                killer_json = None
        if ui_mode == "killerducky" and killer_json is not None:
            game_id = db.add_game(
                killer_json,
                title=title,
                source=result_url or source,
                original_url=original_url,
                result_url=result_url,
                platform="official",
                tags=body.get("tags") or "",
                notes=body.get("notes") or "",
            )
            self.send_json({"kind": "official", "id": game_id})
            return
        game_id = db.add_manual_game(
            title=title,
            source=source,
            platform="official",
            tags=body.get("tags") or "",
            notes=body.get("notes") or "",
            rating_percent=float(rating_percent) if rating_percent not in {None, ""} else None,
            raw_text=html,
            errors=errors,
            total_reviewed=body.get("total_reviewed"),
            total_matches=body.get("total_matches"),
            original_url=original_url,
            result_url=result_url,
            model_tag=body.get("model_tag") or "official-web",
            ui_mode=ui_mode,
        )
        self.send_json({"kind": "official", "id": game_id})

    def handle_official_find(self) -> None:
        body = self.read_json()
        raw = body.get("input") or ""
        parsed = parse_main_input(raw)
        if parsed.kind not in {"majsoul_url", "tenhou_url"}:
            raise ValueError("请粘贴雀魂或天凤牌谱链接。")
        model_tag = body.get("model_tag") or "4.1b"
        game = db.find_official_game_for_ui(parsed.value, model_tag, body.get("ui_mode") or "")
        self.send_json({"found": game is not None, "game": game})

    def handle_error_mark(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "errors" or parts[3] != "mark":
            raise ValueError("invalid error mark path")
        body = self.read_json()
        result = db.toggle_error_mark(int(parts[2]), note=body.get("note") or "")
        self.send_json(result)

    def handle_error_learning(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "errors" or parts[3] != "learning":
            raise ValueError("invalid error learning path")
        body = self.read_json()
        result = db.update_error_learning(
            int(parts[2]),
            note=body.get("note") if "note" in body else None,
            status=body.get("status") if "status" in body else None,
            reviewed=bool(body.get("reviewed")),
            marked=body.get("marked") if isinstance(body.get("marked"), bool) else None,
        )
        self.send_json(result)

    def handle_auth_start(self) -> None:
        start_auth_job()
        self.send_json(auth_status())

    def handle_official_start(self) -> None:
        body = self.read_json()
        start_official_job(body)
        self.send_json(official_status())

    def read_json(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        body = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    db.init_db()
    host = "127.0.0.1"
    port = int(os.environ.get("MORTALCOACH_PORT", "8766"))
    httpd = ThreadingHTTPServer((host, port), AppHandler)
    print(f"MortalCoach running at http://{host}:{port}")
    httpd.serve_forever()


def auth_status() -> dict:
    cfg = load_config()
    with AUTH_LOCK:
        job = dict(AUTH_JOB)
    return {
        "has_access_token": bool(cfg.get("access_token")),
        "majsoul_base": cfg.get("majsoul_base") or "https://game.maj-soul.com",
        "job": job,
    }


def official_status() -> dict:
    with OFFICIAL_LOCK:
        return dict(OFFICIAL_JOB)


def fetch_public_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"user-agent": "MortalCoach/0.1"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def post_public_json(url: str, payload: dict) -> dict | list:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "user-agent": "MortalCoach/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("result_key"):
        result_url = urljoin(url.rsplit("/", 1)[0] + "/", f"result/{data['result_key']}")
        parsed = urlparse(url)
        result_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 2)[0]}/result/{data['result_key']}"
        for _ in range(6):
            time.sleep(1)
            result = fetch_public_json(result_url)
            if not (isinstance(result, dict) and result.get("result_key")):
                return result
        return fetch_public_json(result_url)
    return data


def majsoul_level_text(level_id: int | str | None) -> str:
    try:
        value = int(level_id or 0)
    except (TypeError, ValueError):
        return ""
    rank = value // 100
    step = value % 100
    names = {
        101: "初心",
        102: "雀士",
        103: "雀杰",
        104: "雀豪",
        105: "雀圣",
        106: "魂天",
    }
    base = names.get(rank)
    if not base:
        return str(value)
    return base if rank == 106 else f"{base}{step}"


def sync_majsoul_public_stats(nickname: str) -> dict:
    base = "https://5-data.amae-koromo.com/api/v2/pl4"
    encoded = quote(nickname)
    players = fetch_public_json(f"{base}/search_player/{encoded}")
    if not isinstance(players, list) or not players:
        raise ValueError(f"没有在雀魂牌谱屋公开数据中找到：{nickname}")
    player = next((item for item in players if item.get("nickname") == nickname), players[0])
    account_id = player.get("id")
    if not account_id:
        raise ValueError("雀魂公开数据返回缺少玩家 ID")

    start = 1262304000000
    end = 4102444800000
    mode = 11
    rank_stats = fetch_public_json(f"{base}/player_stats/{account_id}/{start}/{end}?mode={mode}")
    extended_stats = fetch_public_json(f"{base}/player_extended_stats/{account_id}/{start}/{end}?mode={mode}")
    stats = {
        "source": "amae-koromo",
        "scope": "pl4",
        "mode": mode,
        "mode_label": "四麻段位南风",
        "player": player,
        "level_text": majsoul_level_text((rank_stats.get("level") or player.get("level") or {}).get("id")),
        "rank": rank_stats,
        "extended": extended_stats,
    }
    return db.save_majsoul_stats(player.get("nickname") or nickname, account_id, stats)


def build_coach_brief() -> dict:
    stats = db.get_stats()
    games = stats["games"]
    marks = stats["marked_errors"]
    profile = stats["profile"]
    recent = games[-10:]
    avg_q_gap = (
        sum(float(game.get("avg_q_gap") or 0) for game in recent) / len(recent)
        if recent
        else 0.0
    )
    max_gap_game = max(recent, key=lambda game: float(game.get("max_q_gap") or 0), default=None)
    suggestions = []
    if marks:
        suggestions.append(f"错题库已有 {len(marks)} 条，建议今天先复盘收藏错题里的 Top 5。")
    if avg_q_gap > 0.35:
        suggestions.append("最近平均 Q 损失偏高，优先看最大 Q 差和实际排名靠后的选择。")
    if max_gap_game:
        suggestions.append(f"最近最大单谱 Q 差来自《{max_gap_game.get('title')}》，可优先回看。")
    if profile.get("goals"):
        suggestions.append(f"当前训练目标：{profile.get('goals')}")
    if not suggestions:
        suggestions.append("先积累 5-10 份棋盘复盘结果，MortalCoach 就能给出更稳定的趋势建议。")
    return {
        "profile": profile,
        "summary": stats["summary"],
        "recent_count": len(recent),
        "avg_recent_q_gap": avg_q_gap,
        "suggestions": suggestions,
    }


def ratio_value(data: dict, key: str) -> float | None:
    try:
        value = float(data.get(key))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def majsoul_level_text(level_id: int | str | None) -> str:
    try:
        value = int(level_id or 0)
    except (TypeError, ValueError):
        return ""
    rank = value // 100
    step = value % 100
    names = {
        101: "初心",
        102: "雀士",
        103: "雀杰",
        104: "雀豪",
        105: "雀圣",
        106: "魂天",
    }
    base = names.get(rank)
    if not base:
        return str(value)
    return base if rank == 106 else f"{base}{step}"


def sync_majsoul_public_stats(nickname: str) -> dict:
    base = "https://5-data.amae-koromo.com/api/v2/pl4"
    encoded = quote(nickname)
    players = fetch_public_json(f"{base}/search_player/{encoded}")
    if not isinstance(players, list) or not players:
        raise ValueError(f"没有在雀魂牌谱屋公开数据中找到：{nickname}")
    player = next((item for item in players if item.get("nickname") == nickname), players[0])
    account_id = player.get("id")
    if not account_id:
        raise ValueError("雀魂公开数据返回缺少玩家 ID")

    start = 1262304000000
    end = 4102444800000
    mode = 11
    rank_stats = fetch_public_json(f"{base}/player_stats/{account_id}/{start}/{end}?mode={mode}")
    extended_stats = fetch_public_json(f"{base}/player_extended_stats/{account_id}/{start}/{end}?mode={mode}")
    stats = {
        "source": "amae-koromo",
        "scope": "pl4",
        "mode": mode,
        "mode_label": "四麻段位南风",
        "player": player,
        "level_text": majsoul_level_text((rank_stats.get("level") or player.get("level") or {}).get("id")),
        "rank": rank_stats,
        "extended": extended_stats,
    }
    return db.save_majsoul_stats(player.get("nickname") or nickname, account_id, stats)


def build_coach_brief() -> dict:
    stats = db.get_stats()
    games = stats["games"]
    marks = stats["marked_errors"]
    profile = stats["profile"]
    recent = games[-10:]
    avg_q_gap = (
        sum(float(game.get("avg_q_gap") or 0) for game in recent) / len(recent)
        if recent
        else 0.0
    )
    max_gap_game = max(recent, key=lambda game: float(game.get("max_q_gap") or 0), default=None)
    suggestions = []
    if marks:
        suggestions.append(f"错题库已有 {len(marks)} 条，建议今天先复盘收藏错题里的 Top 5。")
    if avg_q_gap > 0.35:
        suggestions.append("最近平均 Q 损失偏高，优先看最大 Q 差和实际排名靠后的选择。")
    if max_gap_game:
        suggestions.append(f"最近最大单谱 Q 差来自《{max_gap_game.get('title')}》，可优先回看。")

    majsoul_stats = profile.get("majsoul_stats") or {}
    extended = majsoul_stats.get("extended") or {}
    rank_stats = majsoul_stats.get("rank") or {}
    if majsoul_stats:
        game_count = extended.get("count") or rank_stats.get("count") or 0
        suggestions.append(
            f"已接入雀魂公开统计（{majsoul_stats.get('mode_label') or '四麻段位'}，{game_count} 局），AI 教练会把长期风格当作训练背景。"
        )
        deal_in = ratio_value(extended, "放铳率")
        call = ratio_value(extended, "副露率")
        riichi = ratio_value(extended, "立直率")
        win = ratio_value(extended, "和牌率")
        avg_rank = ratio_value(rank_stats, "avg_rank")
        if deal_in is not None and deal_in >= 0.13:
            suggestions.append(f"长期放铳率约 {deal_in * 100:.1f}%，训练档案可重点追踪押引和末巡安全度。")
        if call is not None and call >= 0.38:
            suggestions.append(f"副露率约 {call * 100:.1f}%，复盘时建议单独标记副露后的守备与价值判断。")
        if riichi is not None and riichi <= 0.16:
            suggestions.append(f"立直率约 {riichi * 100:.1f}%，后续可以观察是否存在门清进攻不足或过度默听。")
        if win is not None and win <= 0.20:
            suggestions.append(f"和牌率约 {win * 100:.1f}%，可结合 Mortal 错误库检查进攻效率与听牌速度。")
        if avg_rank is not None and avg_rank >= 2.55:
            suggestions.append(f"平均顺位 {avg_rank:.2f}，建议把四位回避相关错题单独做一组训练。")
    elif profile.get("majsoul_id"):
        suggestions.append("训练档案里已有雀魂昵称，可以同步公开统计，让 AI 教练先获得你的长期数据背景。")
    else:
        suggestions.append("填写雀魂昵称并同步公开统计后，AI 教练可以开始建立你的训练档案画像。")

    if profile.get("goals"):
        suggestions.append(f"当前训练目标：{profile.get('goals')}")
    if not suggestions:
        suggestions.append("先积累 5-10 份棋盘复盘结果，MortalCoach 就能给出更稳定的趋势建议。")
    return {
        "profile": profile,
        "summary": stats["summary"],
        "recent_count": len(recent),
        "avg_recent_q_gap": avg_q_gap,
        "suggestions": suggestions,
    }


MAJSOUL_4P_MODES = [
    {"mode": 16, "label": "王座南", "room": "王座之间", "wind": "南风"},
    {"mode": 15, "label": "王座东", "room": "王座之间", "wind": "东风"},
    {"mode": 12, "label": "玉南", "room": "玉之间", "wind": "南风"},
    {"mode": 11, "label": "玉东", "room": "玉之间", "wind": "东风"},
    {"mode": 9, "label": "金南", "room": "金之间", "wind": "南风"},
    {"mode": 8, "label": "金东", "room": "金之间", "wind": "东风"},
]


def majsoul_mode_count(mode_stats: dict) -> int:
    try:
        return int(mode_stats.get("record_count") or 0)
    except (TypeError, ValueError):
        pass
    extended = mode_stats.get("extended") or {}
    rank = mode_stats.get("rank") or {}
    try:
        return int(extended.get("count") or rank.get("count") or 0)
    except (TypeError, ValueError):
        return 0


MAJSOUL_RANK_DELTA_4 = [15, 5, -5, -15]
MAJSOUL_MODE_DELTA_4 = {
    16: [120, 60, 0, 0],
    15: [60, 30, 0, 0],
    12: [110, 55, 0, 0],
    11: [55, 30, 0, 0],
    9: [80, 40, 0, 0],
    8: [40, 20, 0, 0],
}


def format_stable_level(value: float | None) -> str:
    if value is None:
        return ""
    if value >= 4:
        return f"圣{value - 3:.2f}"
    return f"豪{value:.2f}"


def estimate_stable_level(rank_stats: dict, mode: int) -> dict:
    rates = rank_stats.get("rank_rates") or []
    scores = rank_stats.get("rank_avg_score") or []
    mode_delta = MAJSOUL_MODE_DELTA_4.get(mode)
    if len(rates) < 4 or len(scores) < 4 or not mode_delta:
        return {"value": None, "label": ""}
    fourth_rate = float(rates[3] or 0)
    if fourth_rate <= 0:
        return {"value": None, "label": ""}
    expected = 0.0
    for score, rank_delta, uma_delta, rate in zip(scores, MAJSOUL_RANK_DELTA_4, mode_delta, rates):
        expected += (math.ceil((float(score) - 25000) / 1000 + rank_delta) + uma_delta) * float(rate)
    stable = expected / (fourth_rate * 15) - 10
    return {"value": stable, "label": format_stable_level(stable), "expected_point": expected}


def fetch_majsoul_records(base: str, account_id: int | str, start: int, end: int, mode: int) -> list:
    records: list = []
    cursor = end
    for _ in range(40):
        batch = fetch_public_json(
            f"{base}/player_records/{account_id}/{cursor}/{start}?limit=200&mode={mode}&descending=true&tag="
        )
        if not isinstance(batch, list) or not batch:
            break
        records.extend(batch)
        times = [int(item.get("startTime") or item.get("start_time") or cursor) for item in batch]
        next_cursor = min(times) - 1
        if next_cursor >= cursor:
            break
        cursor = next_cursor
    return records


def fetch_majsoul_mode_stats(
    base: str,
    account_id: int | str,
    start: int,
    end: int,
    mode_info: dict,
    detailed: bool = True,
) -> dict:
    mode = mode_info["mode"]
    rank_stats: dict = {}
    extended_stats: dict = {}
    error = ""
    records: list = []
    try:
        records = fetch_majsoul_records(base, account_id, start, end, mode)
    except Exception as exc:
        error = str(exc)
    keys = [item.get("startTime") or item.get("start_time") for item in records]
    keys = [item for item in keys if item]
    if detailed and keys:
        payload = {"keys": keys, "modes": [mode]}
        try:
            rank_stats = post_public_json(f"{base}/player_stats/{account_id}", payload)
        except Exception as exc:
            error = error or str(exc)
        try:
            extended_stats = post_public_json(f"{base}/player_extended_stats/{account_id}", payload)
        except Exception as exc:
            error = error or str(exc)
    record_count = len(records)
    if isinstance(rank_stats, dict):
        rank_stats = {**rank_stats, "count": record_count}
    else:
        rank_stats = {}
    if isinstance(extended_stats, dict):
        extended_stats = {**extended_stats, "record_count": record_count}
    else:
        extended_stats = {}
    stable_level = estimate_stable_level(rank_stats, int(mode)) if detailed and record_count else {"value": None, "label": ""}
    return {
        **mode_info,
        "record_count": record_count,
        "rank": rank_stats,
        "extended": extended_stats,
        "stable_level": stable_level,
        "error": error,
    }


def sync_majsoul_public_stats(nickname: str) -> dict:
    base = "https://5-data.amae-koromo.com/api/v2/pl4"
    encoded = quote(nickname)
    players = fetch_public_json(f"{base}/search_player/{encoded}")
    if not isinstance(players, list) or not players:
        raise ValueError(f"没有在雀魂牌谱屋公开数据中找到：{nickname}")
    player = next((item for item in players if item.get("nickname") == nickname), players[0])
    account_id = player.get("id")
    if not account_id:
        raise ValueError("雀魂公开数据返回缺少玩家 ID")

    start = 1262304000000
    end = 4102444800000
    modes = [fetch_majsoul_mode_stats(base, account_id, start, end, item, detailed=False) for item in MAJSOUL_4P_MODES]
    best_index, best = max(enumerate(modes), key=lambda item: majsoul_mode_count(item[1]), default=(-1, {}))
    if best_index >= 0 and majsoul_mode_count(best):
        best = fetch_majsoul_mode_stats(base, account_id, start, end, MAJSOUL_4P_MODES[best_index], detailed=True)
        modes[best_index] = best
    stats = {
        "source": "amae-koromo",
        "scope": "pl4",
        "player": player,
        "level_text": majsoul_level_text(((best.get("rank") or {}).get("level") or player.get("level") or {}).get("id")),
        "modes": modes,
        "mode": best.get("mode"),
        "mode_label": best.get("label") or "",
        "rank": best.get("rank") or {},
        "extended": best.get("extended") or {},
    }
    return db.save_majsoul_stats(player.get("nickname") or nickname, account_id, stats)


def build_coach_brief() -> dict:
    stats = db.get_stats()
    games = stats["games"]
    marks = stats["marked_errors"]
    profile = stats["profile"]
    recent = games[-10:]
    avg_q_gap = (
        sum(float(game.get("avg_q_gap") or 0) for game in recent) / len(recent)
        if recent
        else 0.0
    )
    max_gap_game = max(recent, key=lambda game: float(game.get("max_q_gap") or 0), default=None)
    suggestions = []
    if marks:
        suggestions.append(f"错题库已有 {len(marks)} 条，建议今天先复盘收藏错题里的 Top 5。")
    if avg_q_gap > 0.35:
        suggestions.append("最近平均 Q 损失偏高，优先看最大 Q 差和实际排名靠后的选择。")
    if max_gap_game:
        suggestions.append(f"最近最大单谱 Q 差来自《{max_gap_game.get('title')}》，可优先回看。")

    majsoul_stats = profile.get("majsoul_stats") or {}
    mode_stats = [item for item in majsoul_stats.get("modes", []) if majsoul_mode_count(item)]
    if majsoul_stats and mode_stats:
        labels = "、".join(f"{item.get('label')} {majsoul_mode_count(item)}局" for item in mode_stats[:4])
        suggestions.append(f"已按牌谱屋段位场拆分训练档案：{labels}。后续建议会优先看对应场次，不再混合金之间、玉之间和王座。")
        dominant = max(mode_stats, key=majsoul_mode_count)
        extended = dominant.get("extended") or {}
        rank_stats = dominant.get("rank") or {}
        dominant_label = dominant.get("label") or "主要场次"
        deal_in = ratio_value(extended, "放铳率")
        call = ratio_value(extended, "副露率")
        riichi = ratio_value(extended, "立直率")
        win = ratio_value(extended, "和牌率")
        avg_rank = ratio_value(rank_stats, "avg_rank")
        if deal_in is not None and deal_in >= 0.13:
            suggestions.append(f"{dominant_label} 放铳率约 {deal_in * 100:.1f}%，训练档案可重点追踪押引和末巡安全度。")
        if call is not None and call >= 0.38:
            suggestions.append(f"{dominant_label} 副露率约 {call * 100:.1f}%，复盘时建议单独标记副露后的守备与价值判断。")
        if riichi is not None and riichi <= 0.16:
            suggestions.append(f"{dominant_label} 立直率约 {riichi * 100:.1f}%，后续可以观察是否存在门清进攻不足或过度默听。")
        if win is not None and win <= 0.20:
            suggestions.append(f"{dominant_label} 和牌率约 {win * 100:.1f}%，可结合 Mortal 错误库检查进攻效率与听牌速度。")
        if avg_rank is not None and avg_rank >= 2.55:
            suggestions.append(f"{dominant_label} 平均顺位 {avg_rank:.2f}，建议把四位回避相关错题单独做一组训练。")
    elif majsoul_stats:
        suggestions.append("已同步雀魂玩家信息，但这些段位场暂时没有公开统计样本。")
    elif profile.get("majsoul_id"):
        suggestions.append("训练档案里已有雀魂昵称，可以同步公开统计，让 AI 教练先获得你的长期数据背景。")
    else:
        suggestions.append("填写雀魂昵称并同步公开统计后，AI 教练可以开始建立你的训练档案画像。")

    if profile.get("goals"):
        suggestions.append(f"当前训练目标：{profile.get('goals')}")
    if not suggestions:
        suggestions.append("先积累 5-10 份棋盘复盘结果，MortalCoach 就能给出更稳定的趋势建议。")
    return {
        "profile": profile,
        "summary": stats["summary"],
        "recent_count": len(recent),
        "avg_recent_q_gap": avg_q_gap,
        "suggestions": suggestions,
    }


def infer_official_ui_mode(html: str) -> str:
    lowered = (html or "").lower()
    if "details.collapse.entry" in lowered or "牌谱检讨" in html or "replay examination" in lowered:
        return "classic"
    return "killerducky" if html else ""


def looks_like_killer_url(url: str) -> bool:
    parsed = urlparse(url or "")
    data_path = parse_qs(parsed.query).get("data", [""])[0]
    lowered = (url or "").lower()
    return "killerducky" in lowered or data_path.endswith(".json") or "/report/" in data_path


def infer_official_result_mode(html: str, url: str = "", killer_json: dict | None = None) -> str:
    if isinstance(killer_json, dict):
        return "killerducky"
    if looks_like_killer_url(url):
        return "killerducky"
    lowered = (html or "").lower()
    board_signals = [
        "killer mortal reviewer",
        "regular_shortnames",
        "round-dec",
        "prev-mismatch",
        "next-mismatch",
        "killer-call",
    ]
    if any(signal in lowered for signal in board_signals):
        return "killerducky"
    return infer_official_ui_mode(html)


def fetch_killer_json(result_url: str) -> dict | None:
    parsed = urlparse(result_url or "")
    data_path = parse_qs(parsed.query).get("data", [""])[0]
    if not data_path or not parsed.scheme or not parsed.netloc:
        return None
    json_url = urljoin(f"{parsed.scheme}://{parsed.netloc}/", data_path)
    with urllib.request.urlopen(json_url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def start_official_job(body: dict) -> None:
    raw = body.get("input") or ""
    if not raw.strip():
        raise ValueError("请先粘贴雀魂或天凤牌谱链接。")
    parsed = parse_main_input(raw)
    if parsed.kind not in {"majsoul_url", "tenhou_url"}:
        raise ValueError("官方 Mortal 自动分析只接受雀魂或天凤牌谱链接；已有结果页或 JSON 请用“仅保存已有结果 / JSON”。")

    with OFFICIAL_LOCK:
        if OFFICIAL_JOB["running"]:
            raise ValueError("已经有一个官方 Mortal 分析任务在运行，请稍等。")
        OFFICIAL_JOB.update(
            {
                "running": True,
                "ok": False,
                "message": "准备打开官方 Mortal 窗口...",
                "game_id": None,
            }
        )

    thread = threading.Thread(target=run_official_job, args=(body,), daemon=True)
    thread.start()


def set_official_message(message: str) -> None:
    with OFFICIAL_LOCK:
        if OFFICIAL_JOB["running"]:
            OFFICIAL_JOB["message"] = message


def run_official_job(body: dict) -> None:
    try:
        title = body.get("title") or "Official Mortal review"
        tags = body.get("tags") or ""
        notes = body.get("notes") or ""
        model_tag = body.get("model_tag") or "4.1b"
        result = run_official_review(
            body.get("input") or "",
            model_tag=model_tag,
            ui_mode=body.get("ui_mode") or "killerducky",
            progress=set_official_message,
        )
        actual_ui_mode = infer_official_result_mode(result.html, result.result_url) or body.get("ui_mode") or "killerducky"
        if False and (body.get("ui_mode") or "killerducky") == "killerducky" and actual_ui_mode == "classic" and not looks_like_killer_url(result.result_url):
            raise ValueError("官方返回的是 Classic 结果，未保存。请重新生成 KillerDucky 棋盘版复盘。")
        killer_json = None
        if actual_ui_mode == "killerducky":
            try:
                killer_json = fetch_killer_json(result.result_url)
            except Exception:
                killer_json = None
        if killer_json is not None:
            game_id = db.add_game(
                killer_json,
                title=title,
                source=result.result_url,
                original_url=result.source_url,
                result_url=result.result_url,
                platform="official",
                tags=tags,
                notes=f"{notes}\n\nOriginal paipu: {result.source_url}".strip(),
            )
        else:
            game_id = db.add_manual_game(
                title=title,
                source=result.source_url,
                platform="official",
                tags=tags,
                notes=f"{notes}\n\nOriginal paipu: {result.source_url}".strip(),
                rating_percent=result.rating_percent,
                raw_text=result.html,
                original_url=result.source_url,
                result_url=result.result_url,
                model_tag=model_tag,
                ui_mode=actual_ui_mode,
            )
        with OFFICIAL_LOCK:
            OFFICIAL_JOB.update(
                {
                    "running": False,
                    "ok": True,
                    "message": f"官方 Mortal 分析已保存。记录 ID: {game_id}",
                    "game_id": game_id,
                }
            )
    except Exception as exc:
        with OFFICIAL_LOCK:
            OFFICIAL_JOB.update(
                {
                    "running": False,
                    "ok": False,
                    "message": str(exc),
                    "game_id": None,
                }
            )


def start_auth_job() -> None:
    with AUTH_LOCK:
        if AUTH_JOB["running"]:
            return
        AUTH_JOB.update({"running": True, "ok": False, "message": "授权向导运行中，请在打开的雀魂窗口中登录。"})
    thread = threading.Thread(target=run_auth_job, daemon=True)
    thread.start()


def run_auth_job() -> None:
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "auth_wizard.py")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode == 0:
            message = output or "雀魂授权已保存。"
            with AUTH_LOCK:
                AUTH_JOB.update({"running": False, "ok": True, "message": message})
        else:
            message = output or f"授权向导退出，代码 {proc.returncode}。"
            with AUTH_LOCK:
                AUTH_JOB.update({"running": False, "ok": False, "message": message})
    except Exception as exc:
        with AUTH_LOCK:
            AUTH_JOB.update({"running": False, "ok": False, "message": str(exc)})


if __name__ == "__main__":
    main()
