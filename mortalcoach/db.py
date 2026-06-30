from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from analysis import extract_errors, summarize_review
from official_parser import parse_official_html


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "mortalcoach.sqlite3"
BACKUP_DIR = DATA_DIR / "backups"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists games (
                id integer primary key autoincrement,
                title text not null,
                source text,
                original_url text,
                result_url text,
                platform text,
                player text,
                tags text,
                notes text,
                created_at text not null,
                rating real not null,
                rating_percent real not null,
                match_rate real not null,
                total_reviewed integer not null,
                total_matches integer not null,
                error_count integer not null,
                max_q_gap real not null,
                avg_q_gap real not null,
                model_tag text,
                raw_json text not null
            );

            create table if not exists review_errors (
                id integer primary key autoincrement,
                game_id integer not null references games(id) on delete cascade,
                kyoku_index integer not null,
                entry_index integer not null,
                round text not null,
                junme integer,
                tiles_left integer,
                shanten integer,
                q_gap real not null,
                actual_rank integer not null,
                expected_json text not null,
                actual_json text not null,
                error_json text not null
            );

            create table if not exists error_marks (
                id integer primary key autoincrement,
                error_id integer not null unique references review_errors(id) on delete cascade,
                game_id integer not null references games(id) on delete cascade,
                note text,
                created_at text not null
            );

            create table if not exists profiles (
                id integer primary key check (id = 1),
                display_name text,
                majsoul_id text,
                tenhou_id text,
                goals text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists error_learning (
                error_id integer primary key references review_errors(id) on delete cascade,
                note text,
                status text not null default 'new',
                review_count integer not null default 0,
                last_reviewed_at text,
                updated_at text not null
            );

            create table if not exists tags (
                id integer primary key autoincrement,
                name text not null unique,
                color text
            );

            create table if not exists game_tags (
                game_id integer not null references games(id) on delete cascade,
                tag_id integer not null references tags(id) on delete cascade,
                primary key (game_id, tag_id)
            );

            create table if not exists error_tags (
                error_id integer not null references review_errors(id) on delete cascade,
                tag_id integer not null references tags(id) on delete cascade,
                primary key (error_id, tag_id)
            );
            """
        )
        ensure_column(conn, "games", "original_url", "text")
        ensure_column(conn, "games", "result_url", "text")
        ensure_column(conn, "games", "archived", "integer not null default 0")
        ensure_column(conn, "games", "review_status", "text not null default 'new'")
        ensure_column(conn, "games", "last_reviewed_at", "text")
        ensure_column(conn, "error_marks", "status", "text not null default 'new'")
        ensure_column(conn, "error_marks", "review_count", "integer not null default 0")
        ensure_column(conn, "error_marks", "last_reviewed_at", "text")
        ensure_column(conn, "profiles", "majsoul_account_id", "text")
        ensure_column(conn, "profiles", "majsoul_stats_json", "text")
        ensure_column(conn, "profiles", "majsoul_stats_updated_at", "text")
        conn.execute("update error_marks set status = 'new' where status = 'reviewing'")
        conn.execute("update error_learning set status = 'new' where status = 'reviewing'")
        backfill_official_columns(conn)
        normalize_official_ui_modes(conn)
        archive_classic_official_games(conn)
        repair_killer_error_tables(conn)


def ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    if column not in {row["name"] for row in rows}:
        conn.execute(f"alter table {table} add column {column} {declaration}")


def backfill_official_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        select id, source, notes, model_tag, original_url, result_url, raw_json
        from games
        where platform = 'official'
        """
    ).fetchall()
    for row in rows:
        original_url = row["original_url"] or extract_original_url(row["notes"] or "", row["raw_json"] or "")
        result_url = row["result_url"] or row["source"] or ""
        model_tag = row["model_tag"] or "official-web"
        if model_tag == "official-web":
            model_tag = extract_model_tag(row["raw_json"] or "") or "4.1b"
        conn.execute(
            "update games set original_url = ?, result_url = ?, model_tag = ? where id = ?",
            (original_url, result_url, model_tag, row["id"]),
        )


def extract_original_url(notes: str, raw_json: str) -> str:
    for text in (notes, raw_json):
        match = re.search(r"https?://[^\s\"'}]+", text)
        if match:
            return match.group(0).rstrip("。).,，")
    return ""


def extract_model_tag(raw_json: str) -> str:
    try:
        raw = json.loads(raw_json)
    except Exception:
        raw = {}
    html = raw.get("raw_text", "") if isinstance(raw, dict) else ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    match = re.search(r"model tag\s+([0-9.]+[a-z]?)", text, re.IGNORECASE)
    return match.group(1) if match else ""


def is_classic_official_html(html: str) -> bool:
    lowered = (html or "").lower()
    return (
        "details.collapse.entry" in lowered
        or "牌谱检讨" in html
        or "replay examination" in lowered
    )


def normalize_official_ui_modes(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "select id, raw_json from games where platform = 'official'"
    ).fetchall()
    for row in rows:
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        html = raw.get("raw_text") or ""
        if raw.get("ui_mode") == "killerducky" and is_classic_official_html(html):
            raw["ui_mode"] = "classic"
            conn.execute(
                "update games set raw_json = ? where id = ?",
                (json.dumps(raw, ensure_ascii=False), row["id"]),
            )


def archive_classic_official_games(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        select id, raw_json
        from games
        where platform = 'official'
          and coalesce(archived, 0) = 0
        """
    ).fetchall()
    for row in rows:
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        html = raw.get("raw_text") or ""
        if effective_ui_mode(raw) == "classic" or is_classic_official_html(html):
            conn.execute("update games set archived = 1 where id = ?", (row["id"],))


def repair_killer_error_tables(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        select id, error_count, raw_json
        from games
        where coalesce(archived, 0) = 0
        """
    ).fetchall()
    for row in rows:
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        if not (isinstance(raw.get("review"), dict) and isinstance(raw.get("mjai_log"), (dict, list))):
            continue
        errors = extract_errors(raw, limit=None)
        expected_count = len(errors)
        current_count = int(row["error_count"] or 0)
        if current_count <= expected_count * 2 + 100:
            continue
        conn.execute("delete from error_marks where game_id = ?", (row["id"],))
        conn.execute("delete from review_errors where game_id = ?", (row["id"],))
        for err in errors:
            conn.execute(
                """
                insert into review_errors (
                    game_id, kyoku_index, entry_index, round, junme, tiles_left,
                    shanten, q_gap, actual_rank, expected_json, actual_json, error_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    err["kyoku_index"],
                    err["entry_index"],
                    err["round"],
                    err.get("junme"),
                    err.get("tiles_left"),
                    err.get("shanten"),
                    err["q_gap"],
                    err["actual_rank"],
                    json.dumps(err.get("expected"), ensure_ascii=False),
                    json.dumps(err.get("actual"), ensure_ascii=False),
                    json.dumps(err, ensure_ascii=False),
                ),
            )
        max_q_gap = errors[0]["q_gap"] if errors else 0.0
        avg_q_gap = sum(e["q_gap"] for e in errors) / len(errors) if errors else 0.0
        conn.execute(
            "update games set error_count = ?, max_q_gap = ?, avg_q_gap = ? where id = ?",
            (expected_count, max_q_gap, avg_q_gap, row["id"]),
        )


def add_game(
    payload: dict[str, Any],
    *,
    title: str,
    source: str = "",
    original_url: str = "",
    result_url: str = "",
    platform: str = "",
    player: str = "",
    tags: str = "",
    notes: str = "",
) -> int:
    init_db()
    summary = summarize_review(payload)
    raw_json = json.dumps(payload, ensure_ascii=False)
    created_at = datetime.now().isoformat(timespec="seconds")

    with connect() as conn:
        cur = conn.execute(
            """
            insert into games (
                title, source, original_url, result_url, platform, player, tags, notes, created_at,
                rating, rating_percent, match_rate, total_reviewed, total_matches,
                error_count, max_q_gap, avg_q_gap, model_tag, raw_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                source,
                original_url,
                result_url,
                platform,
                player,
                tags,
                notes,
                created_at,
                summary["rating"],
                summary["rating_percent"],
                summary["match_rate"],
                summary["total_reviewed"],
                summary["total_matches"],
                summary["error_count"],
                summary["max_q_gap"],
                summary["avg_q_gap"],
                summary["model_tag"],
                raw_json,
            ),
        )
        game_id = int(cur.lastrowid)
        for err in extract_errors(payload, limit=None):
            conn.execute(
                """
                insert into review_errors (
                    game_id, kyoku_index, entry_index, round, junme, tiles_left,
                    shanten, q_gap, actual_rank, expected_json, actual_json, error_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    err["kyoku_index"],
                    err["entry_index"],
                    err["round"],
                    err.get("junme"),
                    err.get("tiles_left"),
                    err.get("shanten"),
                    err["q_gap"],
                    err["actual_rank"],
                    json.dumps(err.get("expected"), ensure_ascii=False),
                    json.dumps(err.get("actual"), ensure_ascii=False),
                    json.dumps(err, ensure_ascii=False),
                ),
            )
        return game_id


def add_manual_game(
    *,
    title: str,
    source: str = "",
    platform: str = "official",
    player: str = "",
    tags: str = "",
    notes: str = "",
    rating_percent: float | None = None,
    raw_text: str = "",
    errors: list[dict[str, Any]] | None = None,
    total_reviewed: int | None = None,
    total_matches: int | None = None,
    original_url: str = "",
    result_url: str = "",
    model_tag: str = "official-web",
    ui_mode: str = "",
) -> int:
    init_db()
    created_at = datetime.now().isoformat(timespec="seconds")
    rating_percent_value = float(rating_percent or 0.0)
    rating = rating_percent_value / 100.0
    stored_errors = errors or []
    error_count = len(stored_errors)
    max_q_gap = max((float(err.get("q_gap") or 0.0) for err in stored_errors), default=0.0)
    avg_q_gap = (
        sum(float(err.get("q_gap") or 0.0) for err in stored_errors) / error_count
        if error_count
        else 0.0
    )
    reviewed = int(total_reviewed or 0)
    matches = int(total_matches or 0)
    match_rate = matches / reviewed if reviewed else 0.0
    raw_json = json.dumps(
        {
            "kind": "official_result_bookmark",
            "source": source,
            "original_url": original_url,
            "result_url": result_url,
            "raw_text": raw_text,
            "errors": stored_errors,
            "ui_mode": ui_mode,
        },
        ensure_ascii=False,
    )

    with connect() as conn:
        cur = conn.execute(
            """
            insert into games (
                title, source, original_url, result_url, platform, player, tags, notes, created_at,
                rating, rating_percent, match_rate, total_reviewed, total_matches,
                error_count, max_q_gap, avg_q_gap, model_tag, raw_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                source,
                original_url,
                result_url,
                platform,
                player,
                tags,
                notes,
                created_at,
                rating,
                rating_percent_value,
                match_rate,
                reviewed,
                matches,
                error_count,
                max_q_gap,
                avg_q_gap,
                model_tag,
                raw_json,
            ),
        )
        game_id = int(cur.lastrowid)
        for idx, err in enumerate(sorted(stored_errors, key=lambda item: float(item.get("q_gap") or 0.0), reverse=True)):
            conn.execute(
                """
                insert into review_errors (
                    game_id, kyoku_index, entry_index, round, junme, tiles_left,
                    shanten, q_gap, actual_rank, expected_json, actual_json, error_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id,
                    int(err.get("kyoku_index") or 0),
                    int(err.get("entry_index") if err.get("entry_index") is not None else idx),
                    str(err.get("round") or "?"),
                    err.get("junme"),
                    err.get("tiles_left"),
                    err.get("shanten"),
                    float(err.get("q_gap") or 0.0),
                    int(err.get("actual_rank") or 0),
                    json.dumps(err.get("expected"), ensure_ascii=False),
                    json.dumps(err.get("actual"), ensure_ascii=False),
                    json.dumps(err, ensure_ascii=False),
                ),
            )
        return game_id


def list_games() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            select id, title, source, original_url, result_url, platform, player, tags, created_at,
                   rating_percent, match_rate, total_reviewed, total_matches,
                   error_count, max_q_gap, avg_q_gap, model_tag,
                   review_status, last_reviewed_at
            from games
            where coalesce(archived, 0) = 0
            order by created_at asc, id asc
            """
        ).fetchall()
    return [dict(row) for row in rows]


def find_official_game(original_url: str, model_tag: str) -> dict[str, Any] | None:
    return find_official_game_for_ui(original_url, model_tag, "")


def find_official_game_for_ui(original_url: str, model_tag: str, ui_mode: str = "") -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            select id, title, source, original_url, result_url, platform, player, tags, created_at,
                   rating_percent, match_rate, total_reviewed, total_matches,
                   error_count, max_q_gap, avg_q_gap, model_tag,
                   review_status, last_reviewed_at, raw_json
            from games
            where platform = 'official'
              and original_url = ?
              and model_tag = ?
              and coalesce(archived, 0) = 0
            order by created_at desc, id desc
            """,
            (original_url, model_tag),
        ).fetchall()
    for row in rows:
        data = dict(row)
        if ui_mode:
            try:
                raw = json.loads(data.get("raw_json") or "{}")
            except Exception:
                raw = {}
            raw_ui = raw.get("ui_mode")
            if raw_ui == "killerducky" and is_classic_official_html(raw.get("raw_text") or ""):
                raw_ui = "classic"
            if not raw_ui and isinstance(raw.get("review"), dict) and isinstance(raw.get("mjai_log"), dict):
                raw_ui = "killerducky"
            if raw_ui != ui_mode:
                continue
        data.pop("raw_json", None)
        return data
    return None


def get_game(game_id: int) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("select * from games where id = ?", (game_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["raw_json"] = json.loads(data["raw_json"])
    return data


def update_game_title(game_id: int, title: str) -> dict[str, Any] | None:
    init_db()
    clean_title = str(title or "").strip()
    if not clean_title:
        raise ValueError("title is required")
    with connect() as conn:
        cur = conn.execute("update games set title = ? where id = ?", (clean_title, game_id))
        if cur.rowcount <= 0:
            return None
    return get_game(game_id)


def get_errors(game_id: int, limit: int = 10, order: str = "chronological") -> list[dict[str, Any]]:
    init_db()
    ensure_official_errors(game_id)
    order_clause = "review_errors.kyoku_index asc, review_errors.entry_index asc, review_errors.id asc"
    if order == "q_gap":
        order_clause = "review_errors.q_gap desc, review_errors.actual_rank desc, review_errors.kyoku_index asc, review_errors.entry_index asc"
    top_filtered = order == "chronological" and limit < 9999
    where_clause = "review_errors.game_id = ?"
    params: tuple[Any, ...] = (game_id, limit)
    if top_filtered:
        where_clause = """
            review_errors.id in (
                select id
                from review_errors
                where game_id = ?
                order by q_gap desc, actual_rank desc, kyoku_index asc, entry_index asc
                limit ?
            )
        """
        params = (game_id, limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select review_errors.id as error_id, review_errors.error_json,
                   error_marks.id is not null as marked,
                   coalesce(error_learning.note, error_marks.note, '') as user_note,
                   coalesce(error_learning.status, error_marks.status, 'new') as learning_status,
                   coalesce(error_learning.review_count, error_marks.review_count, 0) as review_count,
                   coalesce(error_learning.last_reviewed_at, error_marks.last_reviewed_at, '') as last_reviewed_at
            from review_errors
            left join error_marks on error_marks.error_id = review_errors.id
            left join error_learning on error_learning.error_id = review_errors.id
            where {where_clause}
            order by {order_clause}
            {"limit ?" if not top_filtered else ""}
            """,
            params,
        ).fetchall()
    errors = []
    for row in rows:
        err = json.loads(row["error_json"])
        err["error_id"] = row["error_id"]
        err["marked"] = bool(row["marked"])
        err["user_note"] = row["user_note"]
        err["learning_status"] = row["learning_status"]
        err["review_count"] = row["review_count"]
        err["last_reviewed_at"] = row["last_reviewed_at"]
        errors.append(err)
    return errors


def get_review_data(game_id: int, limit: int = 10, order: str = "chronological") -> dict[str, Any] | None:
    ensure_official_errors(game_id)
    game = get_game(game_id)
    if game is None:
        return None
    game["raw_json"] = {
        "kind": game.get("raw_json", {}).get("kind"),
        "has_raw_text": bool(game.get("raw_json", {}).get("raw_text")),
        "has_killer_data": get_killer_data(game_id) is not None,
        "ui_mode": effective_ui_mode(game.get("raw_json", {})),
        "is_classic_html": is_classic_official_html(game.get("raw_json", {}).get("raw_text") or ""),
    }
    return {"game": game, "errors": get_errors(game_id, limit=limit, order=order)}


def get_killer_data(game_id: int) -> dict[str, Any] | None:
    game = get_game(game_id)
    if game is None:
        return None
    raw = game.get("raw_json")
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("review"), dict) and isinstance(raw.get("mjai_log"), (dict, list)):
        return raw
    killer_json = raw.get("killer_json")
    if isinstance(killer_json, dict):
        return killer_json
    return None


def effective_ui_mode(raw: dict[str, Any]) -> str:
    if isinstance(raw.get("review"), dict) and isinstance(raw.get("mjai_log"), (dict, list)):
        return "killerducky"
    ui_mode = raw.get("ui_mode") or ""
    if ui_mode == "killerducky" and is_classic_official_html(raw.get("raw_text") or ""):
        return "classic"
    return ui_mode


def ensure_official_errors(game_id: int) -> None:
    with connect() as conn:
        existing = conn.execute(
            "select error_json from review_errors where game_id = ? order by q_gap desc limit 1",
            (game_id,),
        ).fetchone()
        if existing is not None:
            try:
                sample = json.loads(existing["error_json"] or "{}")
            except Exception:
                sample = {}
            if sample.get("state") and sample.get("candidates"):
                return
        count_row = conn.execute("select count(*) as count from review_errors where game_id = ?", (game_id,)).fetchone()
        if count_row and int(count_row["count"]) > 0 and existing is None:
            return
        row = conn.execute(
            "select raw_json, original_url, model_tag from games where id = ? and platform = 'official'",
            (game_id,),
        ).fetchone()
        if row is None:
            return
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except Exception:
            raw = {}
        if isinstance(raw, dict) and isinstance(raw.get("review"), dict) and isinstance(raw.get("mjai_log"), (dict, list)):
            if count_row and int(count_row["count"]) > 0:
                return
        html = raw.get("raw_text") if isinstance(raw, dict) else ""
        if not html:
            copy_errors_from_sibling(conn, game_id, row["original_url"], row["model_tag"])
            return
        parsed = parse_official_html(html)
        errors = parsed.get("errors") or []
        if not errors:
            copy_errors_from_sibling(conn, game_id, row["original_url"], row["model_tag"])
            return
        replace_errors(conn, game_id, errors)
        rating_percent = parsed.get("rating_percent")
        total_reviewed = int(parsed.get("total_reviewed") or 0)
        total_matches = int(parsed.get("total_matches") or 0)
        updates = {
            "error_count": len(errors),
            "max_q_gap": max((float(err.get("q_gap") or 0.0) for err in errors), default=0.0),
            "avg_q_gap": sum(float(err.get("q_gap") or 0.0) for err in errors) / len(errors),
            "total_reviewed": total_reviewed,
            "total_matches": total_matches,
            "match_rate": total_matches / total_reviewed if total_reviewed else 0.0,
        }
        if rating_percent is not None:
            updates["rating_percent"] = float(rating_percent)
            updates["rating"] = float(rating_percent) / 100.0
        assignments = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(f"update games set {assignments} where id = ?", (*updates.values(), game_id))


def copy_errors_from_sibling(
    conn: sqlite3.Connection,
    game_id: int,
    original_url: str | None,
    model_tag: str | None,
) -> None:
    if not original_url:
        return
    rows = conn.execute(
        """
        select review_errors.error_json
        from review_errors
        join games on games.id = review_errors.game_id
        where games.id != ?
          and games.platform = 'official'
          and games.original_url = ?
          and coalesce(games.model_tag, '') = coalesce(?, '')
        order by games.created_at desc, games.id desc, review_errors.q_gap desc
        """,
        (game_id, original_url, model_tag or ""),
    ).fetchall()
    if not rows:
        return
    errors = [json.loads(row["error_json"]) for row in rows]
    replace_errors(conn, game_id, errors)
    error_count = len(errors)
    conn.execute(
        """
        update games
        set error_count = ?, max_q_gap = ?, avg_q_gap = ?
        where id = ?
        """,
        (
            error_count,
            max((float(err.get("q_gap") or 0.0) for err in errors), default=0.0),
            sum(float(err.get("q_gap") or 0.0) for err in errors) / error_count if error_count else 0.0,
            game_id,
        ),
    )


def replace_errors(conn: sqlite3.Connection, game_id: int, errors: list[dict[str, Any]]) -> None:
    conn.execute("delete from review_errors where game_id = ?", (game_id,))
    for idx, err in enumerate(sorted(errors, key=lambda item: float(item.get("q_gap") or 0.0), reverse=True)):
        conn.execute(
            """
            insert into review_errors (
                game_id, kyoku_index, entry_index, round, junme, tiles_left,
                shanten, q_gap, actual_rank, expected_json, actual_json, error_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                int(err.get("kyoku_index") or 0),
                int(err.get("entry_index") if err.get("entry_index") is not None else idx),
                str(err.get("round") or "?"),
                err.get("junme"),
                err.get("tiles_left"),
                err.get("shanten"),
                float(err.get("q_gap") or 0.0),
                int(err.get("actual_rank") or 0),
                json.dumps(err.get("expected"), ensure_ascii=False),
                json.dumps(err.get("actual"), ensure_ascii=False),
                json.dumps(err, ensure_ascii=False),
            ),
        )


def toggle_error_mark(error_id: int, note: str = "") -> dict[str, Any]:
    with connect() as conn:
        existing = conn.execute("select id from error_marks where error_id = ?", (error_id,)).fetchone()
        if existing is not None:
            conn.execute("delete from error_marks where error_id = ?", (error_id,))
            return {"marked": False}
        row = conn.execute("select game_id from review_errors where id = ?", (error_id,)).fetchone()
        if row is None:
            raise ValueError("error not found")
        now = datetime.now().isoformat(timespec="seconds")
        learning = conn.execute(
            "select note, status, review_count, last_reviewed_at from error_learning where error_id = ?",
            (error_id,),
        ).fetchone()
        conn.execute(
            """
            insert into error_marks (error_id, game_id, note, status, review_count, last_reviewed_at, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                error_id,
                int(row["game_id"]),
                note or (learning["note"] if learning else ""),
                (learning["status"] if learning else "new") or "new",
                int(learning["review_count"] if learning else 0),
                learning["last_reviewed_at"] if learning else None,
                now,
            ),
        )
        return {"marked": True}


def update_error_learning(
    error_id: int,
    *,
    note: str | None = None,
    status: str | None = None,
    reviewed: bool = False,
    marked: bool | None = None,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute("select game_id from review_errors where id = ?", (error_id,)).fetchone()
        if row is None:
            raise ValueError("error not found")
        existing = conn.execute("select * from error_learning where error_id = ?", (error_id,)).fetchone()
        current_note = existing["note"] if existing else ""
        current_status = existing["status"] if existing else "new"
        current_count = int(existing["review_count"] if existing else 0)
        current_last = existing["last_reviewed_at"] if existing else None
        next_note = current_note if note is None else note
        next_status = current_status if status is None else status
        next_count = current_count + 1 if reviewed else current_count
        next_last = now if reviewed else current_last
        conn.execute(
            """
            insert into error_learning (error_id, note, status, review_count, last_reviewed_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(error_id) do update set
                note = excluded.note,
                status = excluded.status,
                review_count = excluded.review_count,
                last_reviewed_at = excluded.last_reviewed_at,
                updated_at = excluded.updated_at
            """,
            (error_id, next_note, next_status or "new", next_count, next_last, now),
        )
        if marked is not None:
            existing_mark = conn.execute("select id from error_marks where error_id = ?", (error_id,)).fetchone()
            if marked and existing_mark is None:
                conn.execute(
                    """
                    insert into error_marks (error_id, game_id, note, status, review_count, last_reviewed_at, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (error_id, int(row["game_id"]), next_note, next_status or "new", next_count, next_last, now),
                )
            if not marked and existing_mark is not None:
                conn.execute("delete from error_marks where error_id = ?", (error_id,))
        conn.execute(
            """
            update error_marks
            set note = ?, status = ?, review_count = ?, last_reviewed_at = ?
            where error_id = ?
            """,
            (next_note, next_status or "new", next_count, next_last, error_id),
        )
        mark = conn.execute("select id from error_marks where error_id = ?", (error_id,)).fetchone()
        if reviewed:
            conn.execute(
                "update games set last_reviewed_at = ?, review_status = 'reviewing' where id = ?",
                (now, int(row["game_id"])),
            )
        return {
            "error_id": error_id,
            "marked": mark is not None,
            "user_note": next_note,
            "learning_status": next_status or "new",
            "review_count": next_count,
            "last_reviewed_at": next_last or "",
        }


def list_marked_errors() -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            select error_marks.id as mark_id, error_marks.created_at as marked_at,
                   coalesce(error_learning.note, error_marks.note, '') as user_note,
                   coalesce(error_learning.status, error_marks.status, 'new') as learning_status,
                   coalesce(error_learning.review_count, error_marks.review_count, 0) as review_count,
                   coalesce(error_learning.last_reviewed_at, error_marks.last_reviewed_at, '') as last_reviewed_at,
                   games.id as game_id, games.title as game_title, games.rating_percent,
                   review_errors.id as error_id, review_errors.error_json
            from error_marks
            join review_errors on review_errors.id = error_marks.error_id
            join games on games.id = review_errors.game_id
            left join error_learning on error_learning.error_id = review_errors.id
            where coalesce(games.archived, 0) = 0
            order by error_marks.created_at desc, error_marks.id desc
            """
        ).fetchall()
    items = []
    for row in rows:
        err = json.loads(row["error_json"])
        err.update(
            {
                "mark_id": row["mark_id"],
                "marked_at": row["marked_at"],
                "game_id": row["game_id"],
                "game_title": row["game_title"],
                "rating_percent": row["rating_percent"],
                "error_id": row["error_id"],
                "marked": True,
                "user_note": row["user_note"],
                "learning_status": row["learning_status"],
                "review_count": row["review_count"],
                "last_reviewed_at": row["last_reviewed_at"],
            }
        )
        items.append(err)
    return items


def get_profile() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        row = conn.execute("select * from profiles where id = 1").fetchone()
    if row is None:
        return {
            "display_name": "",
            "majsoul_id": "",
            "tenhou_id": "",
            "goals": "",
            "majsoul_account_id": "",
            "majsoul_stats": None,
            "majsoul_stats_updated_at": "",
        }
    data = dict(row)
    raw_stats = data.pop("majsoul_stats_json", None)
    try:
        data["majsoul_stats"] = json.loads(raw_stats) if raw_stats else None
    except json.JSONDecodeError:
        data["majsoul_stats"] = None
    return data


def save_profile(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    data = {
        "display_name": str(payload.get("display_name") or ""),
        "majsoul_id": str(payload.get("majsoul_id") or ""),
        "tenhou_id": str(payload.get("tenhou_id") or ""),
        "goals": str(payload.get("goals") or ""),
    }
    with connect() as conn:
        conn.execute(
            """
            insert into profiles (id, display_name, majsoul_id, tenhou_id, goals, created_at, updated_at)
            values (1, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                display_name = excluded.display_name,
                majsoul_id = excluded.majsoul_id,
                tenhou_id = excluded.tenhou_id,
                goals = excluded.goals,
                updated_at = excluded.updated_at
            """,
            (
                data["display_name"],
                data["majsoul_id"],
                data["tenhou_id"],
                data["goals"],
                now,
                now,
            ),
        )
    return get_profile()


def save_majsoul_stats(nickname: str, account_id: int | str, stats: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    profile = get_profile()
    with connect() as conn:
        conn.execute(
            """
            insert into profiles (
                id, display_name, majsoul_id, tenhou_id, goals,
                majsoul_account_id, majsoul_stats_json, majsoul_stats_updated_at,
                created_at, updated_at
            )
            values (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                majsoul_id = excluded.majsoul_id,
                majsoul_account_id = excluded.majsoul_account_id,
                majsoul_stats_json = excluded.majsoul_stats_json,
                majsoul_stats_updated_at = excluded.majsoul_stats_updated_at,
                updated_at = excluded.updated_at
            """,
            (
                profile.get("display_name") or "",
                nickname,
                profile.get("tenhou_id") or "",
                profile.get("goals") or "",
                str(account_id),
                json.dumps(stats, ensure_ascii=False),
                now,
                now,
                now,
            ),
        )
    return get_profile()


def get_stats() -> dict[str, Any]:
    init_db()
    games = list_games()
    marks = list_marked_errors()
    analyzed = len(games)
    ratings = [float(game.get("rating_percent") or 0) for game in games if float(game.get("rating_percent") or 0) > 0]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
    avg_match_rate = (
        sum(float(game.get("match_rate") or 0) for game in games) / analyzed
        if analyzed
        else 0.0
    )
    avg_errors = (
        sum(int(game.get("error_count") or 0) for game in games) / analyzed
        if analyzed
        else 0.0
    )
    return {
        "profile": get_profile(),
        "games": games,
        "marked_errors": marks,
        "summary": {
            "analyzed": analyzed,
            "marked": len(marks),
            "avg_rating": avg_rating,
            "avg_match_rate": avg_match_rate,
            "avg_errors": avg_errors,
            "latest_rating": ratings[-1] if ratings else 0.0,
        },
    }


def create_backup() -> dict[str, Any]:
    init_db()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"mortalcoach-{stamp}.sqlite3"
    shutil.copy2(DB_PATH, target)
    return {
        "ok": True,
        "filename": target.name,
        "path": str(target),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def export_data() -> dict[str, Any]:
    init_db()
    tables = [
        "games",
        "review_errors",
        "error_marks",
        "error_learning",
        "profiles",
        "tags",
        "game_tags",
        "error_tags",
    ]
    json_columns = {
        "games": ["raw_json"],
        "review_errors": ["expected_json", "actual_json", "error_json"],
        "profiles": ["majsoul_stats_json"],
    }
    export: dict[str, Any] = {
        "schema": "mortalcoach.export.v1",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {},
    }
    with connect() as conn:
        for table in tables:
            rows = []
            for row in conn.execute(f"select * from {table}").fetchall():
                item = dict(row)
                for column in json_columns.get(table, []):
                    if not item.get(column):
                        continue
                    try:
                        item[column] = json.loads(item[column])
                    except Exception:
                        pass
                rows.append(item)
            export["tables"][table] = rows
    return export


def delete_game(game_id: int) -> bool:
    init_db()
    with connect() as conn:
        error_rows = conn.execute("select id from review_errors where game_id = ?", (game_id,)).fetchall()
        error_ids = [int(row["id"]) for row in error_rows]
        if error_ids:
            placeholders = ",".join("?" for _ in error_ids)
            conn.execute(f"delete from error_tags where error_id in ({placeholders})", error_ids)
            conn.execute(f"delete from error_learning where error_id in ({placeholders})", error_ids)
            conn.execute(f"delete from error_marks where error_id in ({placeholders})", error_ids)
        conn.execute("delete from game_tags where game_id = ?", (game_id,))
        conn.execute("delete from error_marks where game_id = ?", (game_id,))
        conn.execute("delete from review_errors where game_id = ?", (game_id,))
        cur = conn.execute("delete from games where id = ?", (game_id,))
        return cur.rowcount > 0
